"""Daily NASA NEO Bronze to Silver/Gold pipeline.

Bronze is the immutable raw API payload in S3. Silver/Gold is the normalized
and filtered data loaded into the local project PostgreSQL service (hostname
``postgres`` inside Docker). Airflow metadata uses a separate ``airflow-db``
service and is never mixed with the target database.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import uuid
from typing import Any

import boto3
import pandas as pd
import requests
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import create_engine, text

from etl.common.config import get_nasa_config, get_postgres_config
from etl.transform.asteroid_transform import filter_alerts, normalize_neo_feed

LOGGER = logging.getLogger(__name__)
MONITORING_TABLE = "asteroides_monitoria"

DEFAULT_ARGS = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": dt.timedelta(minutes=5),
}


def _run_date(context: dict[str, Any]) -> dt.date:
    logical_date = context["logical_date"]
    return logical_date.date() if hasattr(logical_date, "date") else logical_date


def _s3_key(run_date: dt.date) -> str:
    prefix = os.getenv("S3_PREFIX", "bronze").strip("/")
    filename = f"raw_nasa_data_{run_date:%Y%m%d}.json"
    return f"{prefix}/{filename}" if prefix else filename


def _s3_client():
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-2"),
        config=Config(
            retries={"total_max_attempts": 4, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )


def ingest_bronze(**context: Any) -> str:
    """Fetch NASA NEO JSON and persist the exact payload in S3."""

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise AirflowException("S3_BUCKET_NAME nao configurado")

    run_date = _run_date(context)
    nasa = get_nasa_config()
    response = requests.get(
        f"{nasa.base_url}/{nasa.resource}",
        params={
            "start_date": run_date.isoformat(),
            "end_date": run_date.isoformat(),
            "api_key": nasa.api_key,
        },
        timeout=30,
    )
    try:
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise AirflowException(f"Falha ao consultar a API NASA: {exc}") from exc

    key = _s3_key(run_date)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    try:
        _s3_client().put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
            Metadata={"source": "nasa-neows", "run-date": run_date.isoformat()},
        )
    except ClientError as exc:
        raise AirflowException(f"Falha ao gravar Bronze no bucket S3: {exc}") from exc

    LOGGER.info("Bronze salvo em s3://%s/%s (%d bytes)", bucket, key, len(body))
    return f"s3://{bucket}/{key}"


def _ensure_target_tables(connection: Any) -> None:
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.asteroides_monitoria (
                id TEXT NOT NULL,
                name TEXT,
                close_approach_date DATE NOT NULL,
                absolute_magnitude_h DOUBLE PRECISION,
                relative_velocity_km_s DOUBLE PRECISION,
                miss_distance_km DOUBLE PRECISION,
                alert_tag TEXT,
                is_potentially_hazardous_asteroid BOOLEAN NOT NULL DEFAULT FALSE,
                details_json JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (id, close_approach_date)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS public.etl_runs (
                id BIGSERIAL PRIMARY KEY,
                run_date DATE NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ NOT NULL,
                objects_received INTEGER NOT NULL DEFAULT 0,
                alerts_loaded INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
    )


def _record_run(engine: Any, run_date: dt.date, started_at: dt.datetime, *, received: int, loaded: int, status: str, error_message: str | None = None) -> None:
    finished_at = dt.datetime.now(dt.timezone.utc)
    with engine.begin() as connection:
        _ensure_target_tables(connection)
        connection.execute(
            text(
                """
                INSERT INTO public.etl_runs
                    (run_date, started_at, finished_at, objects_received,
                     alerts_loaded, status, error_message)
                VALUES
                    (:run_date, :started_at, :finished_at, :received,
                     :loaded, :status, :error_message)
                """
            ),
            {
                "run_date": run_date,
                "started_at": started_at,
                "finished_at": finished_at,
                "received": received,
                "loaded": loaded,
                "status": status,
                "error_message": error_message,
            },
        )


def _upsert_dataframe(connection: Any, dataframe: pd.DataFrame) -> int:
    if dataframe.empty:
        return 0

    # to_sql writes a staging table; the following SQL keeps the target table
    # idempotent on (id, close_approach_date), as required for daily reruns.
    staging = f"_nasa_stage_{uuid.uuid4().hex}"
    try:
        dataframe.to_sql(staging, connection, schema="public", if_exists="replace", index=False, method="multi")
        connection.execute(
            text(
                f"""
                INSERT INTO public.{MONITORING_TABLE} (
                    id, name, close_approach_date, absolute_magnitude_h,
                    relative_velocity_km_s, miss_distance_km, alert_tag,
                    is_potentially_hazardous_asteroid, details_json
                )
                SELECT id, name, close_approach_date, absolute_magnitude_h,
                       relative_velocity_km_s, miss_distance_km, alert_tag,
                       is_potentially_hazardous_asteroid,
                       CAST(details_json AS JSONB)
                FROM public."{staging}"
                ON CONFLICT (id, close_approach_date) DO UPDATE SET
                    name = EXCLUDED.name,
                    absolute_magnitude_h = EXCLUDED.absolute_magnitude_h,
                    relative_velocity_km_s = EXCLUDED.relative_velocity_km_s,
                    miss_distance_km = EXCLUDED.miss_distance_km,
                    alert_tag = EXCLUDED.alert_tag,
                    is_potentially_hazardous_asteroid = EXCLUDED.is_potentially_hazardous_asteroid,
                    details_json = EXCLUDED.details_json
                """
            )
        )
        return len(dataframe)
    finally:
        connection.execute(text(f'DROP TABLE IF EXISTS public."{staging}"'))


def process_silver_gold(**context: Any) -> int:
    """Read Bronze from S3, transform it and upsert Silver/Gold to PostgreSQL."""

    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise AirflowException("S3_BUCKET_NAME nao configurado")
    run_date = _run_date(context)
    started_at = dt.datetime.now(dt.timezone.utc)
    engine = create_engine(get_postgres_config().sqlalchemy_url, pool_pre_ping=True, pool_recycle=300)

    try:
        key = _s3_key(run_date)
        response = _s3_client().get_object(Bucket=bucket, Key=key)
        with response["Body"] as body:
            raw = json.loads(body.read().decode("utf-8"))
        normalized = normalize_neo_feed(raw)
        alerts = filter_alerts(normalized)
        with engine.begin() as connection:
            _ensure_target_tables(connection)
            loaded = _upsert_dataframe(connection, alerts)
        _record_run(engine, run_date, started_at, received=len(normalized), loaded=loaded, status="success")
        LOGGER.info("Silver/Gold concluido: %d recebidos, %d carregados", len(normalized), loaded)
        return loaded
    except ClientError as exc:
        message = f"Falha ao ler Bronze no S3: {exc}"
        _record_run(engine, run_date, started_at, received=0, loaded=0, status="failed", error_message=message)
        raise AirflowException(message) from exc
    except Exception as exc:
        message = str(exc)
        try:
            _record_run(engine, run_date, started_at, received=0, loaded=0, status="failed", error_message=message[:2000])
        except Exception:
            LOGGER.exception("Nao foi possivel registrar falha em etl_runs")
        raise
    finally:
        engine.dispose()


with DAG(
    dag_id="nasa_etl_dag",
    default_args=DEFAULT_ARGS,
    schedule="@daily",
    start_date=dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["nasa", "etl", "neo", "s3-bronze"],
) as dag:
    bronze = PythonOperator(
        task_id="ingest_bronze_to_s3",
        python_callable=ingest_bronze,
    )
    silver_gold = PythonOperator(
        task_id="process_silver_gold_to_postgres",
        python_callable=process_silver_gold,
    )

    bronze >> silver_gold
