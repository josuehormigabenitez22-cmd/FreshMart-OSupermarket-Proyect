"""Detección de días sin datos en gold (``sql/monitoring_gaps.sql``) y alerta a Slack.

    python -m freshmart.quality.gap_detection --gold-dir freshmart-lake/gold --campaign verano
    python -m freshmart.quality.gap_detection ... --desde 2024-06-15 --hasta 2024-09-15 --alert

Sin ``--desde``/``--hasta`` se revisa entre el primer y el último día con datos de la
campaña (huecos internos). Con ``--alert`` se envía la alerta a Slack si hay gaps; el
webhook se lee de ``SLACK_WEBHOOK_URL``. Código de salida 1 si hay gaps: sirve para un
cron o una tarea de Airflow a las 7:00.
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import duckdb

from freshmart.campaigns.cli import parse_campaign
from freshmart.campaigns.config import get_config
from freshmart.campaigns.gold import TABLA_PERFORMANCE
from freshmart.logging_config import configurar_logging
from freshmart.quality.slack_alerts import enviar_alerta_slack
from freshmart.settings import SQL_DIR

logger = logging.getLogger(__name__)

GAPS_SQL = SQL_DIR / "monitoring_gaps.sql"


def _conectar(gold_dir: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE SCHEMA gold")
    ruta = (gold_dir / TABLA_PERFORMANCE / "*.parquet").as_posix().replace("'", "''")
    con.execute(
        f"CREATE VIEW gold.{TABLA_PERFORMANCE} AS SELECT * FROM read_parquet('{ruta}')"
    )
    return con


def rango_con_datos(gold_dir: Path, campana: str) -> tuple[date, date] | None:
    """Primer y último día con datos de la campaña, o None si no hay ninguno."""
    con = _conectar(gold_dir)
    try:
        fila = con.execute(
            f"SELECT CAST(MIN(fecha) AS DATE), CAST(MAX(fecha) AS DATE) "
            f"FROM gold.{TABLA_PERFORMANCE} WHERE campana = ?",
            [campana],
        ).fetchone()
    finally:
        con.close()
    if fila is None or fila[0] is None:
        return None
    return fila[0], fila[1]


def detectar_gaps(gold_dir: Path, campana: str, desde: date, hasta: date) -> list[date]:
    """Días de ``[desde, hasta]`` sin ninguna fila en ``gold.campaign_performance``."""
    if desde > hasta:
        raise ValueError(f"Ventana vacía: desde {desde} > hasta {hasta}")
    con = _conectar(gold_dir)
    try:
        con.execute("SET VARIABLE campana = ?", [campana])
        con.execute("SET VARIABLE desde = CAST(? AS DATE)", [desde.isoformat()])
        con.execute("SET VARIABLE hasta = CAST(? AS DATE)", [hasta.isoformat()])
        filas = con.execute(GAPS_SQL.read_text(encoding="utf-8")).fetchall()
    finally:
        con.close()
    gaps = [fila[0] for fila in filas]
    if gaps:
        logger.warning(
            "%s: %d días sin datos entre %s y %s", campana, len(gaps), desde, hasta
        )
    else:
        logger.info("%s: sin gaps entre %s y %s", campana, desde, hasta)
    return gaps


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detecta días sin datos en gold.")
    parser.add_argument("--gold-dir", type=Path, required=True)
    parser.add_argument("--campaign", type=parse_campaign, required=True)
    parser.add_argument("--desde", type=date.fromisoformat, help="AAAA-MM-DD")
    parser.add_argument("--hasta", type=date.fromisoformat, help="AAAA-MM-DD")
    parser.add_argument(
        "--alert", action="store_true", help="Envía la alerta a Slack si hay gaps."
    )
    args = parser.parse_args(argv)
    configurar_logging()

    campana = get_config(args.campaign).particion
    desde: date | None = args.desde
    hasta: date | None = args.hasta
    if desde is None or hasta is None:
        rango = rango_con_datos(args.gold_dir, campana)
        if rango is None:
            print(f"{campana}: no hay ningún dato en gold; indica --desde y --hasta.")
            return 1
        desde = desde or rango[0]
        hasta = hasta or rango[1]

    gaps = detectar_gaps(args.gold_dir, campana, desde, hasta)
    if not gaps:
        print(f"{campana}: sin gaps entre {desde} y {hasta}.")
        return 0

    print(f"{campana}: {len(gaps)} días sin datos: {', '.join(map(str, gaps))}")
    if args.alert:
        enviar_alerta_slack(gaps, campana)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
