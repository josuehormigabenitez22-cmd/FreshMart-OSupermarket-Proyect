"""Inventario y líneas de pedido con los CSV reales. Se salta si data/ no existe."""

from pathlib import Path

import pandas as pd
import pytest

from freshmart.catalog.silver import run_catalogo
from freshmart.inventory.gold import run_gold_inventario
from freshmart.inventory.silver import run_inventario
from freshmart.orders.lineas import run_lineas
from freshmart.quality.cuarentena import COL_MOTIVO
from freshmart.settings import DATA_DIR

NECESARIOS = [
    "inventario_diario.csv",
    "lineas_pedido.csv",
    "productos.csv",
    "categorias.csv",
]
pytestmark = pytest.mark.skipif(
    not all((DATA_DIR / f).exists() for f in NECESARIOS),
    reason="Faltan CSV reales en data/",
)


@pytest.fixture(scope="module")
def silver(tmp_path_factory: pytest.TempPathFactory) -> Path:
    silver = tmp_path_factory.mktemp("lake") / "silver"
    run_catalogo(DATA_DIR, silver)
    return silver


def test_inventario_real(silver: Path) -> None:
    resultado = run_inventario(DATA_DIR, silver)

    # 18.470 filas − 911 duplicados exactos − 34 con stock negativo.
    assert (resultado.filas, resultado.cuarentena) == (17_525, 34)
    apartadas = pd.read_parquet(silver / "_cuarentena" / "inventario_diario")
    assert set(apartadas[COL_MOTIVO]) == {"stock_negativo"}

    gold = silver.parent / "gold"
    assert run_gold_inventario(silver, gold) == 10  # 5 tiendas × 2 días


def test_lineas_reales(silver: Path) -> None:
    resultado = run_lineas(DATA_DIR, silver)

    assert resultado.filas + resultado.cuarentena == 142_376  # no se pierde ninguna
    assert resultado.cuarentena == 172
    avisos = {r.nombre: r.detalle for r in resultado.informe.avisos}
    assert avisos["precio_cero"].startswith("375 ")
    assert avisos["producto_en_catalogo"].startswith("47 ")
