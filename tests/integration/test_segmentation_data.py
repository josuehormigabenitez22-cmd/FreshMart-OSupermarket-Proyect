"""Tests con los CSV reales. Se saltan si data/ no existe (está en .gitignore)."""

import pandas as pd
import pytest

from freshmart.segmentation.segment import resumen, verificar
from freshmart.settings import DATA_DIR

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "clientes.csv").exists() or not (DATA_DIR / "pedidos.csv").exists(),
    reason="Faltan los CSV reales en data/",
)

# Cifras verificadas sobre clientes DEDUPLICADOS (14.946 clientes únicos).
# Las del curso (2.499 / 1.975 / 10.773 / 6.782 / 349) suman 15.247, que es el
# número de filas de clientes.csv CON duplicados: salen de no deduplicar.
CIFRAS_REALES = {
    "clientes": 14_946,
    "premium": 2_442,
    "regular": 1_938,
    "nuevo": 10_566,
    "sin_pedidos": 6_661,
    "sin_pedidos_desde_junio": 345,
}


def test_cifras_reales_y_pandas_igual_a_sql() -> None:
    df = verificar()
    assert resumen(df) == CIFRAS_REALES


@pytest.mark.skipif(
    not (DATA_DIR / "segmentacion_jorge.csv").exists(),
    reason="Falta segmentacion_jorge.csv",
)
def test_coincide_con_la_referencia_de_jorge_deduplicada() -> None:
    ref = pd.read_csv(DATA_DIR / "segmentacion_jorge.csv").drop_duplicates("cliente_id")
    df = verificar()
    m = df.merge(ref, on="cliente_id", suffixes=("", "_ref"))

    assert len(m) == len(df) == len(ref)
    assert (m["pedidos_3m"] == m["pedidos_3m_ref"]).all()
    assert (m["segmento_calculado"] == m["segmento_calculado_ref"]).all()
