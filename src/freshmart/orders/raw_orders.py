"""Extracción diaria de pedidos de PostgreSQL a la zona raw (DAG raw_orders_daily).

Esta lógica no depende de Airflow para poder testearla sin él. El DAG solo
obtiene la conexión (Airflow Connections) y sube el resultado a S3.

Reglas tras el incidente DATA-162:

* Ninguna credencial en el código: la conexión llega ya abierta desde fuera.
* La query es parametrizada: las fechas viajan como parámetros del driver,
  nunca formateadas dentro del SQL.
* Si la extracción viene vacía se falla en voz alta: un día sin pedidos en
  FreshMart es un síntoma, no un dato.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any, Protocol

import pandas as pd

logger = logging.getLogger(__name__)

FUENTE = "orders"  # base de datos de RDS (orders, users, inventory)
TABLA = "orders"

# Intervalo semiabierto [inicio, fin): vale tanto si order_date es DATE como
# TIMESTAMP. Placeholders con nombre de psycopg2.
ORDERS_QUERY = """
SELECT *
FROM orders
WHERE order_date >= %(inicio)s
  AND order_date <  %(fin)s
"""


class Cursor(Protocol):
    @property
    def description(self) -> Sequence[Sequence[Any]] | None: ...

    def execute(self, query: str, params: Mapping[str, Any]) -> Any: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def close(self) -> Any: ...


class Conexion(Protocol):
    """Lo que necesitamos de una conexión DB-API (psycopg2 la cumple)."""

    def cursor(self) -> Cursor: ...


def raw_orders_key(dia: date) -> str:
    """Clave S3 de la partición del día: raw/{fuente}/{tabla}/{AAAA}/{MM}/{DD}/."""
    return f"raw/{FUENTE}/{TABLA}/{dia.year}/{dia.month:02d}/{dia.day:02d}/{TABLA}.csv"


def extraer_pedidos(
    conexion: Conexion, inicio: datetime, fin: datetime
) -> pd.DataFrame:
    """Pedidos con ``inicio <= order_date < fin``, con la query parametrizada."""
    cursor = conexion.cursor()
    try:
        cursor.execute(ORDERS_QUERY, {"inicio": inicio, "fin": fin})
        filas = cursor.fetchall()
        columnas = [columna[0] for columna in cursor.description or []]
    finally:
        cursor.close()

    df = pd.DataFrame.from_records(filas, columns=columnas)
    logger.info("Pedidos extraídos [%s, %s): %d", inicio, fin, len(df))
    return df


def validar_extraccion(df: pd.DataFrame, dia: date) -> None:
    """Falla si no hay pedidos: mejor un DAG en rojo que una partición vacía en verde."""
    if df.empty:
        raise ValueError(
            f"0 pedidos para {dia.isoformat()}: no se escribe nada en raw. "
            "Revisa la conexión, el filtro de fechas y el sistema de origen."
        )


def a_csv(df: pd.DataFrame) -> str:
    """CSV tal cual sale de la base de datos (raw no transforma nada)."""
    return df.to_csv(index=False)
