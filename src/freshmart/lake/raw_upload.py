"""Ingesta inmutable de los CSV a la zona raw del lake, con manifest.

Reglas: el original se copia sin tocar, un archivo ya subido no se sobrescribe nunca
y ``_manifest.json`` registra ruta relativa, fecha de ingesta y sha256 de cada archivo.
Ejecutarlo dos veces no cambia ni un byte.
"""

import argparse
import hashlib
import json
import logging
import shutil
from datetime import date
from pathlib import Path, PureWindowsPath
from typing import Any

from freshmart.lake.paths import raw_table_path
from freshmart.logging_config import configurar_logging
from freshmart.settings import DATA_DIR, RAW_DIR

logger = logging.getLogger(__name__)

SOURCE = "marketing"

# Archivo -> fuente (raw/{fuente}/{tabla}/...). Los primeros llegaron todos por
# Marketing y ya están subidos con esa fuente: raw es inmutable, no se mueven.
FILES: dict[str, str] = {
    # Campaña de primavera
    "campana_primavera_ventas.csv": SOURCE,
    # Campaña de verano
    "campana_verano_clientes.csv": SOURCE,
    "campana_verano_ventas.csv": SOURCE,
    "productos_promo_verano.csv": SOURCE,
    # Datos generales
    "clientes.csv": SOURCE,
    "pedidos.csv": SOURCE,
    # Catálogo (lo necesita la capa gold)
    "productos.csv": SOURCE,
    "categorias.csv": SOURCE,
    # Operaciones
    "inventario_diario.csv": "inventory",
    "lineas_pedido.csv": "orders",
}

MANIFEST_PATH = RAW_DIR / "_manifest.json"


def sha256_file(path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()

    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(8192), b""):
            sha256.update(bloque)

    return sha256.hexdigest()


def _es_ruta_absoluta(ruta: str) -> bool:
    # Las primeras versiones guardaban rutas absolutas de Windows (C:\...): se
    # detectan también cuando se ejecuta en Linux/macOS.
    return Path(ruta).is_absolute() or PureWindowsPath(ruta).is_absolute()


def cargar_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    """Registros del manifest indexados por ruta relativa a raw.

    Descarta los registros antiguos con ruta absoluta: dependen de la máquina en la que
    se generaron y duplicaban a los relativos.
    """
    if not manifest_path.exists():
        return {}

    with manifest_path.open(encoding="utf-8") as archivo:
        manifest: list[dict[str, Any]] = json.load(archivo)

    registros = {r["path"]: r for r in manifest if not _es_ruta_absoluta(r["path"])}
    descartados = len(manifest) - len(registros)
    if descartados:
        logger.warning(
            "Manifest: %d registros antiguos con ruta absoluta descartados", descartados
        )
    return registros


def upload_raw(
    data_dir: Path = DATA_DIR,
    raw_dir: Path = RAW_DIR,
    ingestion_date: date = date(2024, 9, 16),
) -> None:
    """Copia archivos a raw sin sobrescribir los originales."""
    manifest_path = raw_dir / "_manifest.json"
    raw_dir.mkdir(parents=True, exist_ok=True)
    registros = cargar_manifest(manifest_path)

    for nombre, fuente in FILES.items():
        origen = data_dir / nombre

        if not origen.is_file():
            logger.warning("Archivo no encontrado, se omite: %s", origen)
            continue

        tabla = Path(nombre).stem
        destino_dir = raw_table_path(
            raw_dir=raw_dir,
            source=fuente,
            table=tabla,
            ingestion_date=ingestion_date,
        )
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / nombre

        # Solo copiamos si el original todavía no existe.
        if destino.exists():
            sha_destino = sha256_file(destino)
            if sha256_file(origen) != sha_destino:
                logger.warning(
                    "%s ha cambiado respecto a lo subido en raw y NO se sobrescribe. "
                    "Si es una versión nueva, súbela con otra fecha de ingesta (--date).",
                    nombre,
                )
            else:
                logger.info("Ya existe, no se sobrescribe: %s", destino)
        else:
            shutil.copy2(origen, destino)
            sha_destino = sha256_file(destino)
            logger.info("Copiado: %s", nombre)

        ruta_relativa = destino.relative_to(raw_dir).as_posix()
        registro_anterior = registros.get(ruta_relativa)

        registros[ruta_relativa] = {
            "source": fuente,
            "table": tabla,
            "file": nombre,
            "path": ruta_relativa,
            "ingestion_date": (
                registro_anterior["ingestion_date"]
                if registro_anterior
                else ingestion_date.isoformat()
            ),
            "sha256": sha_destino,
        }

    nuevo_manifest = (
        json.dumps(
            list(registros.values()),
            indent=4,
            ensure_ascii=False,
        )
        + "\n"
    )

    contenido_actual = (
        manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
    )

    if contenido_actual != nuevo_manifest:
        manifest_path.write_text(
            nuevo_manifest,
            encoding="utf-8",
        )
        logger.info("Manifest actualizado: %s", manifest_path)
    else:
        logger.info("Manifest sin cambios: %s", manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingesta idempotente de archivos en el data lake."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_DIR,
        help="Directorio de los CSV originales.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RAW_DIR,
        help="Directorio raw del data lake.",
    )
    parser.add_argument(
        "--date",
        default="2024-09-16",
        help="Fecha de ingesta en formato AAAA-MM-DD.",
    )
    args = parser.parse_args()
    configurar_logging()

    upload_raw(
        data_dir=args.input,
        raw_dir=args.output,
        ingestion_date=date.fromisoformat(args.date),
    )


if __name__ == "__main__":
    main()
