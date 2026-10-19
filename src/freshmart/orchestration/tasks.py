"""Tareas que ejecutan los DAGs de Airflow (``dags/``), sin importar Airflow.

Cada función es una tarea: recibe rutas como texto (Airflow las pasa desde Variables
con plantillas Jinja), lanza una excepción si la tarea debe fallar y devuelve algo
pequeño y serializable (va a XCom). Así la lógica se testea sin Airflow y el DAG solo
dice el orden.
"""

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from freshmart.campaigns.config import Campaign, get_config
from freshmart.campaigns.gold import run_gold
from freshmart.campaigns.pipeline import run_pipeline
from freshmart.catalog.silver import run_catalogo
from freshmart.inventory.gold import run_gold_inventario
from freshmart.inventory.silver import run_inventario
from freshmart.orders.lineas import run_lineas
from freshmart.quality.csv_validator import validar_csv_campana
from freshmart.quality.gap_detection import detectar_gaps, rango_con_datos
from freshmart.quality.slack_alerts import enviar_alerta_slack

logger = logging.getLogger(__name__)


class CsvNoValidoError(Exception):
    """El CSV de entrada no pasa el validador: no se procesa (fail fast)."""


# --- Campañas (DAG semanal) -----------------------------------------------------


def tarea_validar_csv(campana: str, input_dir: str) -> int:
    """Valida el CSV de la campaña antes de procesarlo. Devuelve el número de avisos."""
    campaign = Campaign(campana)
    df = pd.read_csv(Path(input_dir) / get_config(campaign).archivo, dtype=str)
    informe = validar_csv_campana(df, campaign)
    logger.info("%s", informe.resumen())
    if not informe.ok:
        raise CsvNoValidoError(informe.resumen())
    return len(informe.avisos)


def tarea_silver_campana(campana: str, input_dir: str, silver_dir: str) -> int:
    """Limpieza + validación + silver. Si falla una validación lanza y no escribe nada."""
    return run_pipeline(Campaign(campana), Path(input_dir), Path(silver_dir)).filas


def tarea_catalogo(input_dir: str, silver_dir: str) -> int:
    return run_catalogo(Path(input_dir), Path(silver_dir)).productos


def tarea_gold(silver_dir: str, gold_dir: str) -> int:
    return run_gold(Path(silver_dir), Path(gold_dir)).performance


def tarea_gaps(campana: str, gold_dir: str) -> list[str]:
    """Busca días sin datos en gold y avisa a Slack si los hay.

    No falla la tarea: el aviso a Slack ya es la acción, y un DAG en rojo duplicaría la
    alerta en #data-alerts. Devuelve los días afectados (vacío si todo va bien).
    """
    particion = get_config(Campaign(campana)).particion
    rango = rango_con_datos(Path(gold_dir), particion)
    if rango is None:
        raise RuntimeError(f"gold no tiene ningún dato de {particion}")
    gaps: list[date] = detectar_gaps(Path(gold_dir), particion, *rango)
    enviar_alerta_slack(gaps, particion)
    return [d.isoformat() for d in gaps]


# --- Operaciones (DAG diario) -------------------------------------------------------


def tarea_inventario(input_dir: str, silver_dir: str, gold_dir: str) -> dict[str, int]:
    resultado = run_inventario(Path(input_dir), Path(silver_dir))
    filas_gold = run_gold_inventario(Path(silver_dir), Path(gold_dir))
    return {
        "silver": resultado.filas,
        "cuarentena": resultado.cuarentena,
        "gold": filas_gold,
    }


def tarea_lineas(input_dir: str, silver_dir: str) -> dict[str, int]:
    resultado = run_lineas(Path(input_dir), Path(silver_dir))
    return {"silver": resultado.filas, "cuarentena": resultado.cuarentena}
