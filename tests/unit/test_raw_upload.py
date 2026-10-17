import hashlib
import json
from datetime import date
from pathlib import Path

from freshmart.lake.raw_upload import upload_raw


def test_upload_raw_is_idempotent(tmp_path: Path) -> None:
    # Preparamos directorios temporales.
    data_dir = tmp_path / "data"
    raw_dir = tmp_path / "raw"
    data_dir.mkdir()

    # Creamos un CSV de prueba.
    nombre = "campana_primavera_ventas.csv"
    contenido_original = "id,precio\n1,10.5\n"
    (data_dir / nombre).write_text(
        contenido_original,
        encoding="utf-8",
    )

    fecha = date(2024, 9, 16)

    # Primera ejecución.
    upload_raw(
        data_dir=data_dir,
        raw_dir=raw_dir,
        ingestion_date=fecha,
    )

    archivo_destino = (
        raw_dir / "marketing" / Path(nombre).stem / "2024" / "09" / "16" / nombre
    )
    manifest_path = raw_dir / "_manifest.json"

    contenido_destino_1 = archivo_destino.read_bytes()
    contenido_manifest_1 = manifest_path.read_bytes()

    # Cambiamos el origen para comprobar que no se sobrescribe el destino.
    (data_dir / nombre).write_text(
        "id,precio\n2,99.9\n",
        encoding="utf-8",
    )

    # Segunda ejecución.
    upload_raw(
        data_dir=data_dir,
        raw_dir=raw_dir,
        ingestion_date=fecha,
    )

    # El archivo original y el manifiesto deben permanecer iguales.
    assert archivo_destino.read_bytes() == contenido_destino_1
    assert manifest_path.read_bytes() == contenido_manifest_1

    # El hash registrado corresponde al archivo almacenado.
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    registro = next(item for item in manifest if item["file"] == nombre)

    hash_esperado = hashlib.sha256(contenido_destino_1).hexdigest()
    assert registro["sha256"] == hash_esperado
    assert registro["ingestion_date"] == fecha.isoformat()
