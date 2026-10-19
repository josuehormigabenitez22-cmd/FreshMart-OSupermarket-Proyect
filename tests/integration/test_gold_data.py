"""Capa gold con los CSV reales. Se salta si data/ no existe (.gitignore).

Cifras de referencia verificadas (ver .claude/skills/freshmart-contexto).
"""

from pathlib import Path

import pandas as pd
import pytest

from freshmart.campaigns.config import Campaign
from freshmart.campaigns.gold import (
    clientes_nuevos_por_campana,
    run_gold,
    verificar_gold,
)
from freshmart.campaigns.pipeline import run_pipeline
from freshmart.catalog.silver import run_catalogo
from freshmart.settings import DATA_DIR

NECESARIOS = [
    "campana_verano_ventas.csv",
    "campana_primavera_ventas.csv",
    "productos.csv",
    "categorias.csv",
    "pedidos.csv",
    "clientes.csv",
]
pytestmark = pytest.mark.skipif(
    not all((DATA_DIR / f).exists() for f in NECESARIOS),
    reason="Faltan CSV reales en data/",
)


@pytest.fixture(scope="module")
def lake(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    raiz = tmp_path_factory.mktemp("lake")
    silver, gold = raiz / "silver", raiz / "gold"
    for campaign in Campaign:
        run_pipeline(campaign, DATA_DIR, silver)
    run_catalogo(DATA_DIR, silver)
    run_gold(silver, gold)
    return silver, gold


def test_performance_166_filas_y_revenue_de_referencia(lake: tuple[Path, Path]) -> None:
    performance = pd.read_parquet(lake[1] / "campaign_performance")
    assert len(performance) == 166
    assert performance.groupby("campana").size().to_dict() == {
        "primavera": 76,
        "verano": 90,
    }

    totales = performance.groupby("campana")[
        ["revenue_bruto", "revenue_neto", "num_transacciones"]
    ].sum()
    assert totales["revenue_neto"].round().to_dict() == {
        "primavera": 750_622,
        "verano": 996_555,
    }
    assert totales["revenue_bruto"].round().to_dict() == {
        "primavera": 790_729,
        "verano": 1_048_754,
    }
    ticket = (totales["revenue_neto"] / totales["num_transacciones"]).round(2)
    assert ticket.to_dict() == {"primavera": 24.06, "verano": 23.32}


def test_top_products_de_referencia(lake: tuple[Path, Path]) -> None:
    top = pd.read_parquet(lake[1] / "campaign_top_products")
    primeros = top[top["ranking"] == 1].set_index("campana")
    assert primeros.loc["verano", "producto_nombre"] == "Helado de fresa Häagen-Dazs 1L"
    assert primeros.loc["primavera", "producto_nombre"] == "Vino rosado Protos 75cl"
    assert round(primeros.loc["verano", "revenue_neto"]) == 20_021
    assert top.groupby("campana").size().to_dict() == {"primavera": 50, "verano": 50}


def test_gold_pandas_igual_a_sql(lake: tuple[Path, Path]) -> None:
    verificar_gold(lake[0])


def test_clientes_nuevos_de_referencia() -> None:
    resultado = clientes_nuevos_por_campana(
        pd.read_csv(DATA_DIR / "pedidos.csv", dtype=str),
        pd.read_csv(DATA_DIR / "clientes.csv", dtype=str),
    ).set_index("campana")
    assert resultado.to_dict("index") == {
        "verano": {"primera_compra": 4_769, "registro_nuevo": 667},
        "primavera": {"primera_compra": 3_479, "registro_nuevo": 840},
    }
