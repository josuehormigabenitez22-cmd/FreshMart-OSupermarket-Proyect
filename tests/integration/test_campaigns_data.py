"""Limpieza sobre los CSV reales. Se salta si data/ no existe (.gitignore)."""

import pandas as pd
import pytest

from freshmart.campaigns.clean import leer_campana, limpiar_campana
from freshmart.campaigns.config import Campaign, get_config
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
