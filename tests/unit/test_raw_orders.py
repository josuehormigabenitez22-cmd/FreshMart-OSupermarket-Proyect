from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

import pandas as pd
import pytest

from freshmart.orders.raw_orders import (
    ORDERS_QUERY,
    a_csv,
    extraer_pedidos,
    raw_orders_key,
    validar_extraccion,
)

INICIO = datetime(2024, 9, 18)
FIN = datetime(2024, 9, 19)


class CursorFalso:
    """Registra lo que recibe el driver en lugar de ir a PostgreSQL."""

    def __init__(self, filas: list[tuple[Any, ...]], columnas: list[str]) -> None:
        self._filas = filas
        self.description: Sequence[Sequence[Any]] = [(c,) for c in columnas]
        self.llamadas: list[tuple[str, Mapping[str, Any]]] = []
        self.cerrado = False

    def execute(self, query: str, params: Mapping[str, Any]) -> None:
        self.llamadas.append((query, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._filas

    def close(self) -> None:
        self.cerrado = True


class ConexionFalsa:
    def __init__(self, cursor: CursorFalso) -> None:
        self._cursor = cursor

    def cursor(self) -> CursorFalso:
        return self._cursor


def test_raw_orders_key_sigue_la_convencion_del_lake() -> None:
    assert raw_orders_key(date(2024, 9, 8)) == "raw/orders/orders/2024/09/08/orders.csv"


def test_extraer_pedidos_pasa_las_fechas_como_parametros() -> None:
    cursor = CursorFalso([(1, "2024-09-18 10:00")], ["order_id", "order_date"])

    df = extraer_pedidos(ConexionFalsa(cursor), INICIO, FIN)

    assert df.to_dict("records") == [{"order_id": 1, "order_date": "2024-09-18 10:00"}]
    [(query, params)] = cursor.llamadas
    assert query == ORDERS_QUERY  # el SQL no se modifica con los valores
    assert params == {"inicio": INICIO, "fin": FIN}
    assert cursor.cerrado


def test_query_no_interpola_valores() -> None:
    # Solo placeholders con nombre: nada de f-strings ni fechas literales.
    assert "%(inicio)s" in ORDERS_QUERY
    assert "%(fin)s" in ORDERS_QUERY
    assert "2024" not in ORDERS_QUERY
    assert "{" not in ORDERS_QUERY


def test_extraer_pedidos_cierra_el_cursor_aunque_falle() -> None:
    class CursorQueFalla(CursorFalso):
        def execute(self, query: str, params: Mapping[str, Any]) -> None:
            raise RuntimeError("password authentication failed")

    cursor = CursorQueFalla([], [])
    with pytest.raises(RuntimeError, match="authentication"):
        extraer_pedidos(ConexionFalsa(cursor), INICIO, FIN)
    assert cursor.cerrado


def test_validar_extraccion_caso_feliz() -> None:
    validar_extraccion(pd.DataFrame({"order_id": [1]}), date(2024, 9, 18))


def test_validar_extraccion_vacia_falla() -> None:
    vacio = pd.DataFrame(columns=["order_id"])
    with pytest.raises(ValueError, match="0 pedidos para 2024-09-18"):
        validar_extraccion(vacio, date(2024, 9, 18))


def test_a_csv_sin_indice() -> None:
    df = pd.DataFrame({"order_id": [1, 2], "estado": ["entregado", "cancelado"]})
    assert a_csv(df).splitlines() == ["order_id,estado", "1,entregado", "2,cancelado"]
