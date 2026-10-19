"""DAG raw_orders_daily: pedidos del día anterior de PostgreSQL (RDS) a raw en S3.

Versión definitiva tras el incidente DATA-162 (ver
docs/incidents/DATA-162_postmortem.md). Ninguna credencial vive en este repo.

Requisitos en Airflow (2.7+):

* Paquetes: ``freshmart-osupermarket`` (este repo), ``apache-airflow-providers-postgres``
  y ``apache-airflow-providers-amazon``.
* Connection ``freshmart_orders_ro`` (tipo Postgres, usuario ``data_readonly``).
  Recomendado: secrets backend de AWS Secrets Manager
  (``airflow.providers.amazon.aws.secrets.secrets_manager.SecretsManagerBackend``),
  así la Connection se lee de Secrets Manager en cada ejecución y la rotación
  trimestral de Infra no obliga a tocar código ni a redesplegar.
* Connection ``aws_default`` con permiso de escritura en ``s3://freshmart-lake/raw/orders/``.

Cada run procesa su ``data_interval`` (el día anterior a la ejecución) y escribe
``raw/orders/orders/AAAA/MM/DD/orders.csv``. Relanzar un día reescribe su partición
con el mismo resultado: es idempotente.

Recuperar días caídos: con ``catchup=False``, "Trigger DAG" crea un run con la
fecha de HOY y no rellena los días perdidos. Hay que hacer Clear de los runs
fallidos (Browse → DAG Runs → seleccionar → Clear) o, por CLI, con sus fechas
lógicas. Ojo: el run que se ejecuta el día 18 a las 03:00 tiene fecha lógica 17
(procesa el día 17). Para DATA-162 (ejecuciones del 18 y 19 fallidas):

    airflow tasks clear raw_orders_daily -s 2024-09-17 -e 2024-09-18 --yes
"""

from datetime import timedelta

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.postgres.hooks.postgres import PostgresHook

from freshmart.orders.raw_orders import (
    a_csv,
    extraer_pedidos,
    raw_orders_key,
    validar_extraccion,
)

POSTGRES_CONN_ID = "freshmart_orders_ro"
AWS_CONN_ID = "aws_default"
BUCKET = "freshmart-lake"


def extract_orders(
    data_interval_start: pendulum.DateTime,
    data_interval_end: pendulum.DateTime,
    **_: object,
) -> str:
    """Extrae los pedidos del intervalo y los sube a raw. Devuelve la clave S3."""
    dia = data_interval_start.date()

    conexion = PostgresHook(postgres_conn_id=POSTGRES_CONN_ID).get_conn()
    try:
        pedidos = extraer_pedidos(conexion, data_interval_start, data_interval_end)
    finally:
        conexion.close()

    validar_extraccion(pedidos, dia)

    clave = raw_orders_key(dia)
    S3Hook(aws_conn_id=AWS_CONN_ID).load_string(
        a_csv(pedidos), key=clave, bucket_name=BUCKET, replace=True
    )
    return f"s3://{BUCKET}/{clave}"


with DAG(
    dag_id="raw_orders_daily",
    description="Pedidos del día anterior de RDS (orders) a s3://freshmart-lake/raw/",
    schedule="0 3 * * *",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=1),
    default_args={
        "owner": "data-engineering",
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["raw", "orders", "DATA-162"],
) as dag:
    PythonOperator(task_id="extract_orders", python_callable=extract_orders)
