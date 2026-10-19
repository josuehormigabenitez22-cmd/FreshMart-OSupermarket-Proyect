"""Limpieza sobre los CSV reales. Se salta si data/ no existe (.gitignore)."""

from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns import clean
from freshmart.campaigns.clean import leer_campana, limpiar_campana
from freshmart.campaigns.config import Campaign, get_config
from freshmart.campaigns.pipeline import run_pipeline
from freshmart.campaigns.validate import FECHAS_EN_RANGO, validar
from freshmart.settings import DATA_DIR

pytestmark = pytest.mark.skipif(
    not all((DATA_DIR / get_config(c).archivo).exists() for c in Campaign),
    reason="Faltan los CSV de campaña en data/",
)


def test_verano_real() -> None:
    df = limpiar_campana(leer_campana(Campaign.VERANO), Campaign.VERANO)
    assert len(df) == 42_891 - 155 - 3  # duplicados exactos y cantidad = 0
    assert df["fecha_compra"].notna().all()
    assert df["fecha_compra"].min().month == 6  # nada de fechas en diciembre
    assert df["fecha_compra"].max() <= pd.Timestamp("2024-09-30")
    assert df["precio"].between(0.5, 25).all()
    assert df["cliente_anonimo"].sum() > 0


def test_primavera_real() -> None:
    df = limpiar_campana(leer_campana(Campaign.PRIMAVERA), Campaign.PRIMAVERA)
    assert len(df) == 31_204
    assert df["fecha_compra"].dt.month.between(3, 5).all()
    assert df["cliente_anonimo"].sum() == 78
    assert (df["cliente_id"].dropna() > 0).all()  # no queda ningún -1


def test_pipeline_verano_real_42733_filas_y_6_de_6(tmp_path: Path) -> None:
    resultado = run_pipeline(Campaign.VERANO, DATA_DIR, tmp_path / "silver")

    assert resultado.filas == 42_733
    assert (resultado.informe.aprobadas, resultado.informe.total) == (6, 6)
    assert len(pd.read_parquet(tmp_path / "silver" / "campaign_ventas")) == 42_733


def test_pipeline_primavera_real_31204_filas_y_6_de_6(tmp_path: Path) -> None:
    resultado = run_pipeline(Campaign.PRIMAVERA, DATA_DIR, tmp_path / "silver")

    assert resultado.filas == 31_204
    assert (resultado.informe.aprobadas, resultado.informe.total) == (6, 6)


def test_parseo_mixed_dayfirst_del_curso_falla_solo_fechas_en_rango(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def parseo_del_curso(fechas: pd.Series) -> pd.Series:
        return pd.to_datetime(fechas, format="mixed", dayfirst=True)

    monkeypatch.setattr(clean, "parsear_fechas", parseo_del_curso)
    df = clean.limpiar_campana(leer_campana(Campaign.VERANO), Campaign.VERANO)
    informe = validar(df, Campaign.VERANO)

    fallos = [r.nombre for r in informe.resultados if not r.ok]
    assert fallos == [FECHAS_EN_RANGO]
