"""DAG campaign_pipeline_weekly: campañas de Marketing de CSV a dashboard cada lunes.

Lo pidió Laura en la demo: "¿podemos tener esto actualizado automáticamente cada lunes?".
Hace a mano lo que hasta ahora se lanzaba con ``scripts/ejecutar_pipeline.py``:

    validar_csv_<campaña> ─► silver_<campaña> ─┐
                              silver_catalogo ─┴─► gold ─► gaps_<campaña>

* Si el CSV de una campaña no es válido, esa rama se para antes de tocar silver.
* gold solo se reconstruye si todas las campañas y el catálogo han ido bien.
* ``gaps_<campaña>`` avisa a Slack si faltan días (webhook en ``SLACK_WEBHOOK_URL``).

Requisitos en Airflow: el paquete ``freshmart-osupermarket`` instalado y las Variables
``freshmart_input_dir`` (CSV de entrada) y ``freshmart_lake_dir`` (raíz del lake).
Ninguna credencial en este archivo: la guarda de ``tests/unit/test_dags.py`` lo comprueba.
"""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from freshmart.campaigns.config import Campaign, get_config
from freshmart.orchestration.tasks import (
    tarea_catalogo,
    tarea_gaps,
    tarea_gold,
    tarea_silver_campana,
    tarea_validar_csv,
)

INPUT_DIR = "{{ var.value.freshmart_input_dir }}"
SILVER_DIR = "{{ var.value.freshmart_lake_dir }}/silver"
GOLD_DIR = "{{ var.value.freshmart_lake_dir }}/gold"

with DAG(
    dag_id="campaign_pipeline_weekly",
    description="Campañas de Marketing: CSV → silver → gold, con validación y gaps",
    schedule="0 6 * * 1",  # lunes 06:00, antes del standup
    start_date=pendulum.datetime(2024, 9, 23, tz="Europe/Madrid"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args={
        "owner": "data-engineering",
        # Un reintento por si falla la lectura del bucket. Los errores de datos no se
        # arreglan reintentando (lección de DATA-162): fallan y se miran.
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["campañas", "marketing", "DATA-147"],
) as dag:
    catalogo = PythonOperator(
        task_id="silver_catalogo",
        python_callable=tarea_catalogo,
        op_kwargs={"input_dir": INPUT_DIR, "silver_dir": SILVER_DIR},
    )
    gold = PythonOperator(
        task_id="gold",
        python_callable=tarea_gold,
        op_kwargs={"silver_dir": SILVER_DIR, "gold_dir": GOLD_DIR},
    )
    catalogo >> gold

    for campaign in Campaign:
        nombre = get_config(campaign).particion
        validar = PythonOperator(
            task_id=f"validar_csv_{nombre}",
            python_callable=tarea_validar_csv,
            op_kwargs={"campana": campaign.value, "input_dir": INPUT_DIR},
        )
        silver = PythonOperator(
            task_id=f"silver_{nombre}",
            python_callable=tarea_silver_campana,
            op_kwargs={
                "campana": campaign.value,
                "input_dir": INPUT_DIR,
                "silver_dir": SILVER_DIR,
            },
        )
        gaps = PythonOperator(
            task_id=f"gaps_{nombre}",
            python_callable=tarea_gaps,
            op_kwargs={"campana": campaign.value, "gold_dir": GOLD_DIR},
        )
        validar >> silver >> gold >> gaps
