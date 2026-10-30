"""Weekly JSON backup for the project-local PostgreSQL database."""

from __future__ import annotations

import datetime as dt
import logging
import os

import boto3
from airflow import DAG
from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator
from botocore.config import Config
from botocore.exceptions import ClientError
from sqlalchemy import create_engine

from etl.backup.json_email import create_backup_archive, send_backup_email, validate_email_config
from etl.common.config import get_postgres_config

LOGGER = logging.getLogger(__name__)


def create_and_send_backup(**context: object) -> str:
    """Export local project tables, persist the archive to S3, and email it."""
    bucket = os.getenv("S3_BUCKET_NAME", "").strip()
    if not bucket:
        raise AirflowException("S3_BUCKET_NAME nao configurado")
    try:
        validate_email_config()
    except ValueError as exc:
        raise AirflowException(str(exc)) from exc

    created_at = dt.datetime.now(dt.timezone.utc)
    engine = create_engine(
        get_postgres_config().sqlalchemy_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    try:
        archive = create_backup_archive(engine)
    finally:
        engine.dispose()

    prefix = os.getenv("S3_PREFIX", "bronze").strip("/")
    key = f"{prefix + '/' if prefix else ''}backups/nasa-etl-{created_at:%Y%m%dT%H%M%SZ}.json.gz"
    s3 = boto3.client(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-2"),
        config=Config(
            retries={"total_max_attempts": 4, "mode": "standard"},
            connect_timeout=5,
            read_timeout=30,
        ),
    )
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=archive,
            ContentType="application/gzip",
            ServerSideEncryption="AES256",
            Metadata={"backup-format": "nasa-etl-json-v1", "created-at": created_at.isoformat()},
        )
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            # Keep the bearer URL short-lived. AWS credentials from an EC2
            # instance profile can expire before a longer URL's requested TTL.
            ExpiresIn=60 * 60,
        )
    except ClientError as exc:
        raise AirflowException(f"Falha ao gravar backup no S3: {exc}") from exc

    object_uri = f"s3://{bucket}/{key}"
    delivery = send_backup_email(
        archive,
        object_uri=object_uri,
        download_url=url,
        created_at=created_at,
    )
    LOGGER.info(
        "Backup semanal salvo em %s (%d bytes); e-mail enviado (%s)",
        object_uri,
        len(archive),
        delivery,
    )
    return object_uri


with DAG(
    dag_id="nasa_weekly_json_backup",
    schedule="0 3 * * 0",
    start_date=dt.datetime(2024, 1, 7, tzinfo=dt.timezone.utc),
    catchup=False,
    max_active_runs=1,
    tags=["nasa", "backup", "weekly", "postgres", "s3"],
) as dag:
    PythonOperator(
        task_id="export_postgres_json_and_email",
        python_callable=create_and_send_backup,
        retries=2,
        retry_delay=dt.timedelta(minutes=10),
    )
