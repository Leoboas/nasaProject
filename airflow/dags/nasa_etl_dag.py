from __future__ import annotations

import datetime as dt
import os
import requests

from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.models.baseoperator import chain
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from plugins.operators.nasa_extract_operator import NASAExtractOperator
from plugins.operators.nasa_transform_operator import NASATransformOperator
from plugins.operators.nasa_load_operator import NASALoadOperator

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": dt.timedelta(minutes=5),
}


def check_env_and_api(**context):
    """Valida variaveis obrigatorias e conecta na NASA API para healthcheck."""
    required = ["NASA_API_KEY"]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise AirflowException(f"Variaveis obrigatorias ausentes: {', '.join(missing)}")

    api_key = os.getenv("NASA_API_KEY")
    base = os.getenv("NASA_API_BASE", "https://api.nasa.gov")
    resource = os.getenv("NASA_API_RESOURCE", "neo/rest/v1/feed")
    url = f"{base}/{resource}"
    today = dt.date.today().isoformat()
    params = {"start_date": today, "end_date": today, "api_key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=10)
    except Exception as exc:
        raise AirflowException(f"Falha de conexao no healthcheck NASA API: {exc}") from exc
    if resp.status_code != 200:
        raise AirflowException(
            f"Healthcheck NASA API falhou: status={resp.status_code} body={resp.text[:200]}"
        )
    return True


with DAG(
    dag_id="nasa_etl_dag",
    default_args=DEFAULT_ARGS,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["nasa", "etl", "neo"],
) as dag:
    healthcheck = PythonOperator(
        task_id="healthcheck_env_and_api",
        python_callable=check_env_and_api,
    )

    extract = NASAExtractOperator(
        task_id="extract_nasa_neo",
        output_path="/opt/airflow/data/samples/neo_raw_{{ ds }}.json",
    )

    transform = NASATransformOperator(
        task_id="transform_neo",
        input_path="/opt/airflow/data/samples/neo_raw_{{ ds }}.json",
        output_path="/opt/airflow/data/processed/neo_alertas_{{ ds }}.csv",
    )

    load = NASALoadOperator(
        task_id="load_postgres",
        input_path="/opt/airflow/data/processed/neo_alertas_{{ ds }}.csv",
        table_name="asteroides_monitoria",
    )

    chain(healthcheck, extract, transform, load)
