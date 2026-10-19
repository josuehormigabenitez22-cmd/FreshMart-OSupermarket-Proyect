"""DAG operations_daily: inventario y líneas de pedido de raw a silver/gold cada día.

Une el inventario al mismo esquema que las campañas: misma limpieza, mismas
validaciones (``freshmart.quality``), mismo Parquet atómico y la misma cuarentena para
las filas imposibles (stock negativo, precios negativos, totales que no cuadran).

    silver_catalogo ─┬─► inventario (silver + gold inventario_tienda_dia)
                     └─► lineas_pedido (silver)

Se ejecuta a las 05:00, después de ``raw_orders_daily`` (03:00), que deja los pedidos
del día anterior en raw.

Requisitos: el paquete instalado y las Variables ``freshmart_input_dir`` y
``freshmart_lake_dir``. Sin credenciales en el código.
"""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from freshmart.orchestration.tasks import tarea_catalogo, tarea_inventario, tarea_lineas

INPUT_DIR = "{{ var.value.freshmart_input_dir }}"
SILVER_DIR = "{{ var.value.freshmart_lake_dir }}/silver"
GOLD_DIR = "{{ var.value.freshmart_lake_dir }}/gold"

with DAG(
    dag_id="operations_daily",
    description="Inventario y líneas de pedido: CSV → silver (con cuarentena) → gold",
    schedule="0 5 * * *",
    start_date=pendulum.datetime(2024, 9, 23, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=1),
    default_args={
        "owner": "data-engineering",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["inventario", "pedidos", "operaciones"],
) as dag:
    catalogo = PythonOperator(
        task_id="silver_catalogo",
        python_callable=tarea_catalogo,
        op_kwargs={"input_dir": INPUT_DIR, "silver_dir": SILVER_DIR},
    )
    inventario = PythonOperator(
        task_id="inventario",
        python_callable=tarea_inventario,
        op_kwargs={
            "input_dir": INPUT_DIR,
            "silver_dir": SILVER_DIR,
            "gold_dir": GOLD_DIR,
        },
    )
    lineas = PythonOperator(
        task_id="lineas_pedido",
        python_callable=tarea_lineas,
        op_kwargs={"input_dir": INPUT_DIR, "silver_dir": SILVER_DIR},
    )
    catalogo >> [inventario, lineas]
