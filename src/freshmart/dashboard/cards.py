"""Cards del dashboard de campañas (``sql/dashboard_cards.sql``) ejecutadas con DuckDB.

En producción cada card es una pregunta SQL de Metabase contra el warehouse. En local
se preparan las mismas tablas con DuckDB para poder ejecutarlas, testearlas y enseñar
los números en la demo:

    python -m freshmart.dashboard.cards --gold-dir freshmart-lake/gold --input data
"""

import argparse
import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from freshmart.campaigns.gold import TABLA_PERFORMANCE, TABLA_TOP_PRODUCTS
from freshmart.logging_config import configurar_logging
from freshmart.settings import SQL_DIR

CARDS_SQL = SQL_DIR / "dashboard_cards.sql"
PEDIDOS_CSV = "pedidos.csv"

_MARCA_CARD = re.compile(r"^-- name: (\w+)\s*$", re.MULTILINE)


def leer_cards(path: Path = CARDS_SQL) -> dict[str, str]:
    """Separa el archivo en queries por la marca ``-- name: <card>``."""
    texto = path.read_text(encoding="utf-8")
    partes = _MARCA_CARD.split(texto)
    # partes = [cabecera, nombre1, sql1, nombre2, sql2, ...]
    cards = {
        nombre: sql.strip()
        for nombre, sql in zip(partes[1::2], partes[2::2], strict=True)
    }
    if not cards:
        raise ValueError(f"{path} no contiene ninguna card '-- name: ...'")
    return cards


def _ruta_sql(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def conectar(gold_dir: Path, data_dir: Path) -> duckdb.DuckDBPyConnection:
    """Conexión DuckDB con las tablas que leen las cards."""
    con = duckdb.connect()
    con.execute("CREATE SCHEMA gold")
    for tabla in (TABLA_PERFORMANCE, TABLA_TOP_PRODUCTS):
        ruta = _ruta_sql(gold_dir / tabla / "*.parquet")
        con.execute(f"CREATE VIEW gold.{tabla} AS SELECT * FROM read_parquet('{ruta}')")

    # pedidos.csv trae dos formatos de fecha y cliente_id como '108333.0'; en el
    # warehouse ya son TIMESTAMP y BIGINT. La vista lo deja igual que allí.
    pedidos = _ruta_sql(data_dir / PEDIDOS_CSV)
    con.execute(
        f"""
        CREATE VIEW pedidos AS
        SELECT
            CAST(CAST(cliente_id AS DOUBLE) AS BIGINT) AS cliente_id,
            COALESCE(
                try_strptime(fecha_pedido, '%Y-%m-%d %H:%M:%S'),
                try_strptime(fecha_pedido, '%d/%m/%Y %H:%M')
            ) AS fecha_pedido,
            estado
        FROM read_csv('{pedidos}', header = true, all_varchar = true)
        """
    )
    return con


def ejecutar_cards(
    gold_dir: Path, data_dir: Path, path: Path = CARDS_SQL
) -> dict[str, pd.DataFrame]:
    con = conectar(gold_dir, data_dir)
    try:
        return {
            nombre: con.execute(sql).df() for nombre, sql in leer_cards(path).items()
        }
    finally:
        con.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ejecuta las 4 cards del dashboard de campañas."
    )
    parser.add_argument("--gold-dir", type=Path, required=True)
    parser.add_argument(
        "--input", type=Path, required=True, help="Directorio con pedidos.csv."
    )
    args = parser.parse_args(argv)
    configurar_logging()

    for nombre, df in ejecutar_cards(args.gold_dir, args.input).items():
        print(f"\n=== {nombre} ({len(df)} filas) ===")
        print(df.head(12).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
