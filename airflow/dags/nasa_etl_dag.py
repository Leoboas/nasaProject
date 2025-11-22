from __future__ import annotations

import datetime as dt

from airflow import DAG
from airflow.models.baseoperator import chain
from airflow.utils.dates import days_ago

from airflow.plugins.operators.nasa_extract_operator import NASAExtractOperator
from airflow.plugins.operators.nasa_transform_operator import NASATransformOperator
from airflow.plugins.operators.nasa_load_operator import NASALoadOperator

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 1,
    "retry_delay": dt.timedelta(minutes=5),
}

with DAG(
    dag_id="nasa_etl_dag",
    default_args=DEFAULT_ARGS,
    schedule_interval="@daily",
    start_date=days_ago(1),
    catchup=False,
    tags=["nasa", "etl", "neo"],
) as dag:
    extract = NASAExtractOperator(
        task_id="extract_nasa_neo",
        output_path="/opt/airflow/data/samples/neo_raw_{{ ds }}.json",
    )

    transform = NASATransformOperator(
        task_id="transform_neo",
        input_path="/opt/airflow/data/samples/neo_raw_{{ ds }}.json",
        output_path="/opt/airflow/data/processed/neo_{{ ds }}.csv",
    )

    load = NASALoadOperator(
        task_id="load_postgres",
        input_path="/opt/airflow/data/processed/neo_{{ ds }}.csv",
        table_name="neo_asteroids",
    )

    chain(extract, transform, load)
