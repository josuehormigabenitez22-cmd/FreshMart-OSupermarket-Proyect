"""Validador de CSV con los archivos reales. Se salta si data/ no existe (.gitignore)."""

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign, get_config
from freshmart.quality.csv_validator import validar_csv_campana
from freshmart.settings import DATA_DIR

pytestmark = pytest.mark.skipif(
    not all((DATA_DIR / get_config(c).archivo).exists() for c in Campaign),
    reason="Faltan los CSV de campaña en data/",
)


def _detalles(campaign: Campaign) -> tuple[bool, dict[str, str]]:
    df = pd.read_csv(DATA_DIR / get_config(campaign).archivo, dtype=str)
    informe = validar_csv_campana(df, campaign)
    return informe.ok, {r.nombre: r.detalle for r in informe.resultados if not r.ok}


def test_verano_valido_con_avisos_de_formatos_y_duplicados() -> None:
    ok, avisos = _detalles(Campaign.VERANO)
    assert ok  # se puede procesar: la limpieza resuelve ambos avisos
    assert avisos == {
        "formatos_fecha_compra": (
            "3 formatos: {'AAAA-MM-DD': 30157, 'DD/MM/AAAA': 10646, 'Mon D, AAAA': 2088}"
        ),
        "duplicados_exactos": "155 filas duplicadas",
    }


def test_primavera_sin_avisos() -> None:
    assert _detalles(Campaign.PRIMAVERA) == (True, {})
