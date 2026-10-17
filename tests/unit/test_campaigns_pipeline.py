import argparse
from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign
from freshmart.campaigns.pipeline import (
    PARQUET_FILE,
    SILVER_TABLE,
    escribir_silver,
    parse_campaign,
    partition_dir,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "venta_id": pd.array([1, 2], dtype="Int64"),
            "precio": [1.5, 2.5],
            "campana": ["verano_2024", "verano_2024"],
        }
    )


def test_partition_dir_usa_el_nombre_corto_de_la_campana(tmp_path: Path) -> None:
    assert partition_dir(tmp_path, Campaign.VERANO) == (
        tmp_path / SILVER_TABLE / "campana=verano"
    )
    assert partition_dir(tmp_path, Campaign.PRIMAVERA).name == "campana=primavera"


def test_escribir_silver_caso_feliz_sin_la_columna_de_particion(tmp_path: Path) -> None:
    destino = escribir_silver(_df(), tmp_path, Campaign.VERANO)
    assert destino.name == "campana=verano"

    contenido = pd.read_parquet(destino / PARQUET_FILE)
    assert "campana" not in contenido.columns  # la aporta la partición
    assert contenido["venta_id"].tolist() == [1, 2]


def test_escribir_silver_reemplaza_la_particion_y_no_deja_temporales(
    tmp_path: Path,
) -> None:
    escribir_silver(_df(), tmp_path, Campaign.VERANO)
    escribir_silver(_df().iloc[:1], tmp_path, Campaign.VERANO)

    tabla = tmp_path / SILVER_TABLE
    assert [p.name for p in tabla.iterdir()] == ["campana=verano"]  # sin .tmp
    assert len(pd.read_parquet(tabla / "campana=verano" / PARQUET_FILE)) == 1


def test_escribir_silver_no_toca_otras_particiones(tmp_path: Path) -> None:
    escribir_silver(_df(), tmp_path, Campaign.PRIMAVERA)
    antes = (partition_dir(tmp_path, Campaign.PRIMAVERA) / PARQUET_FILE).read_bytes()
    escribir_silver(_df(), tmp_path, Campaign.VERANO)
    despues = (partition_dir(tmp_path, Campaign.PRIMAVERA) / PARQUET_FILE).read_bytes()
    assert antes == despues


def test_parse_campaign_acepta_valor_del_enum_y_nombre_corto() -> None:
    assert parse_campaign("verano_2024") is Campaign.VERANO
    assert parse_campaign("primavera") is Campaign.PRIMAVERA


def test_parse_campaign_desconocida_da_error() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="otoño"):
        parse_campaign("otoño")
