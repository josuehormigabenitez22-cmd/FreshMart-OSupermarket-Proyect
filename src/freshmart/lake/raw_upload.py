import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

from freshmart.lake.paths import raw_table_path
from freshmart.settings import DATA_DIR, RAW_DIR

SOURCE = "marketing"

FILES = [
    # Campaña de primavera
    "campana_primavera_ventas.csv",
    # Campaña de verano
    "campana_verano_clientes.csv",
    "campana_verano_ventas.csv",
    "productos_promo_verano.csv",
    # Datos generales
    "clientes.csv",
    "pedidos.csv",
    # Catálogo (lo necesita la capa gold)
    "productos.csv",
    "categorias.csv",
]

MANIFEST_PATH = RAW_DIR / "_manifest.json"


def sha256_file(path: Path) -> str:
    """Calcula el hash SHA-256 de un archivo."""
    sha256 = hashlib.sha256()

    with path.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(8192), b""):
            sha256.update(bloque)

    return sha256.hexdigest()


def upload_raw(
    data_dir: Path = DATA_DIR,
    raw_dir: Path = RAW_DIR,
    ingestion_date: date = date(2024, 9, 16),
) -> None:
    """Copia archivos a raw sin sobrescribir los originales."""
    manifest_path = raw_dir / "_manifest.json"
    raw_dir.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8") as archivo:
            manifest = json.load(archivo)
    else:
        manifest = []

    # Indexamos los registros existentes por ruta.
    registros = {registro["path"]: registro for registro in manifest}

    for nombre in FILES:
        origen = data_dir / nombre

        if not origen.is_file():
            print(f"Archivo no encontrado: {origen}")
            continue

        tabla = Path(nombre).stem
        destino_dir = raw_table_path(
            raw_dir=raw_dir,
            source=SOURCE,
            table=tabla,
            ingestion_date=ingestion_date,
        )
        destino_dir.mkdir(parents=True, exist_ok=True)
        destino = destino_dir / nombre

        # Solo copiamos si el original todavía no existe.
        if destino.exists():
            print(f"Ya existe, no se sobrescribe: {destino}")
        else:
            shutil.copy2(origen, destino)
            print(f"Copiado: {nombre}")

        ruta_relativa = destino.relative_to(raw_dir).as_posix()
        registro_anterior = registros.get(ruta_relativa)

        registros[ruta_relativa] = {
            "source": SOURCE,
            "table": tabla,
            "file": nombre,
            "path": ruta_relativa,
            "ingestion_date": (
                registro_anterior["ingestion_date"]
                if registro_anterior
                else ingestion_date.isoformat()
            ),
            "sha256": sha256_file(destino),
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

    print(f"Manifest actualizado: {manifest_path}")


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

    upload_raw(
        data_dir=args.input,
        raw_dir=args.output,
        ingestion_date=date.fromisoformat(args.date),
    )


if __name__ == "__main__":
    main()
