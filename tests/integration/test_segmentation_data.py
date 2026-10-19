"""Tests con los CSV reales. Se saltan si data/ no existe (está en .gitignore)."""

import pandas as pd
import pytest

from freshmart.segmentation.segment import CAMPANA_CSV, resumen, verificar
from freshmart.settings import DATA_DIR

pytestmark = pytest.mark.skipif(
    not all(
        (DATA_DIR / f).exists() for f in (CAMPANA_CSV, "clientes.csv", "pedidos.csv")
    ),
    reason="Faltan los CSV reales en data/",
)

# Una fila por cliente de la campaña: 14.946 clientes.
CIFRAS_POR_CLIENTE = {
    "clientes": 14_946,
    "premium": 2_442,
    "regular": 1_938,
    "nuevo": 10_566,
    "sin_pedidos": 6_661,
    "sin_pedidos_desde_junio": 345,
}

# Las cifras del curso (2.499 / 1.975 / 10.773, 6.782 sin pedidos, 349 desde junio)
# no salen de olvidar deduplicar la maestra: cuentan las 15.247 FILAS de la lista de la
# campaña, donde un cliente aparece una vez por canal de contacto.
CIFRAS_POR_CONTACTO = {
    "clientes": 15_247,
    "premium": 2_499,
    "regular": 1_975,
    "nuevo": 10_773,
    "sin_pedidos": 6_782,
    "sin_pedidos_desde_junio": 349,
}


def test_cifras_por_cliente_y_pandas_igual_a_sql() -> None:
    assert resumen(verificar()) == CIFRAS_POR_CLIENTE


def test_contando_contactos_de_la_campana_salen_las_cifras_del_curso() -> None:
    contactos = pd.read_csv(DATA_DIR / CAMPANA_CSV, usecols=["cliente_id"])
    por_contacto = contactos.merge(verificar(), on="cliente_id", how="left")
    assert resumen(por_contacto) == CIFRAS_POR_CONTACTO


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
