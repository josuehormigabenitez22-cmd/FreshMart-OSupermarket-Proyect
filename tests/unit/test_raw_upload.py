import hashlib
import json
import logging
from datetime import date
from pathlib import Path

import pytest

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


def _subir(tmp_path: Path, contenido: str) -> tuple[Path, Path]:
    data_dir, raw_dir = tmp_path / "data", tmp_path / "raw"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "clientes.csv").write_text(contenido, encoding="utf-8")
    upload_raw(data_dir=data_dir, raw_dir=raw_dir, ingestion_date=date(2024, 9, 16))
    return data_dir, raw_dir


def test_upload_raw_avisa_si_el_origen_cambio(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _subir(tmp_path, "id\n1\n")
    with caplog.at_level(logging.INFO, logger="freshmart.lake.raw_upload"):
        _subir(tmp_path, "id\n2\n")
    assert "clientes.csv ha cambiado" in caplog.text
    assert "--date" in caplog.text


def test_upload_raw_sin_cambios_no_avisa(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _subir(tmp_path, "id\n1\n")
    with caplog.at_level(logging.WARNING, logger="freshmart.lake.raw_upload"):
        _subir(tmp_path, "id\n1\n")
    assert "ha cambiado" not in caplog.text


def test_upload_raw_descarta_registros_con_ruta_absoluta(tmp_path: Path) -> None:
    _, raw_dir = _subir(tmp_path, "id\n1\n")
    manifest_path = raw_dir / "_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    antiguo = dict(manifest[0], path="C:\\Users\\x\\raw\\marketing\\clientes.csv")
    manifest_path.write_text(json.dumps([antiguo, *manifest]), encoding="utf-8")

    _subir(tmp_path, "id\n1\n")

    rutas = [r["path"] for r in json.loads(manifest_path.read_text(encoding="utf-8"))]
    assert rutas == ["marketing/clientes/2024/09/16/clientes.csv"]
