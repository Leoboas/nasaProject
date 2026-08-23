"""Execução leve, sem Airflow, do mesmo fluxo diário da DAG.

Este módulo é usado pela EC2 pequena via systemd. O modo Airflow continua
disponível para demonstração local e para ambientes com mais memória.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Protocol

from etl.common.logging_config import get_logger
from etl.extract.nasa_client import NASAClient
from etl.load.postgres_loader import PostgresLoader
from etl.transform.asteroid_transform import filter_alerts, normalize_neo_feed

logger = get_logger(__name__)
DEFAULT_ARTIFACT_RETENTION_DAYS = 90


class NASAFeedClient(Protocol):
    """Contrato mínimo para permitir testes sem chamada externa."""

    def fetch_neo_feed(self, start_date: dt.date, end_date: dt.date | None = None) -> dict:
        ...


class DataFrameLoader(Protocol):
    """Contrato mínimo para permitir testes sem PostgreSQL."""

    def load_dataframe(self, dataframe) -> int:
        ...


def _artifact_retention_days() -> int:
    value = os.getenv("DATA_RETENTION_DAYS", str(DEFAULT_ARTIFACT_RETENTION_DAYS))
    try:
        days = int(value)
    except ValueError:
        logger.warning(
            "DATA_RETENTION_DAYS=%r é inválido; usando %s dias.",
            value,
            DEFAULT_ARTIFACT_RETENTION_DAYS,
        )
        return DEFAULT_ARTIFACT_RETENTION_DAYS
    if days < 1:
        logger.warning(
            "DATA_RETENTION_DAYS deve ser maior que zero; usando %s dias.",
            DEFAULT_ARTIFACT_RETENTION_DAYS,
        )
        return DEFAULT_ARTIFACT_RETENTION_DAYS
    return days


def _cleanup_old_artifacts(root: Path, retention_days: int) -> int:
    cutoff = dt.datetime.now().timestamp() - dt.timedelta(days=retention_days).total_seconds()
    deleted = 0
    for directory, pattern in (
        (root / "samples", "neo_raw_*.json"),
        (root / "processed", "neo_alertas_*.csv"),
    ):
        if not directory.exists():
            continue
        for artifact in directory.glob(pattern):
            if artifact.is_file() and artifact.stat().st_mtime < cutoff:
                artifact.unlink()
                deleted += 1
    if deleted:
        logger.info("Removidos %s artefatos com mais de %s dias.", deleted, retention_days)
    return deleted


def run_daily_etl(
    *,
    run_date: dt.date | None = None,
    data_dir: str | Path | None = None,
    client: NASAFeedClient | None = None,
    loader: DataFrameLoader | None = None,
    retention_days: int | None = None,
) -> int:
    """Extrai, filtra, persiste artefatos e faz upsert dos alertas.

    O retorno é a quantidade de registros enviados ao storage. A função é
    idempotente no PostgreSQL porque o loader usa a chave (id, data).
    """

    started_at = dt.datetime.now(dt.timezone.utc)
    execution_date = run_date or dt.date.today()
    root = Path(data_dir or os.getenv("DATA_DIR", "data"))
    samples_dir = root / "samples"
    processed_dir = root / "processed"
    samples_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_old_artifacts(root, retention_days or _artifact_retention_days())

    api_client = client or NASAClient()
    raw = api_client.fetch_neo_feed(execution_date)

    raw_path = samples_dir / f"neo_raw_{execution_date.isoformat()}.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    normalized = normalize_neo_feed(raw)
    alerts = filter_alerts(normalized)
    processed_path = processed_dir / f"neo_alertas_{execution_date.isoformat()}.csv"
    alerts.to_csv(processed_path, index=False)

    target_loader = loader or PostgresLoader(table_name="asteroides_monitoria")
    loaded = target_loader.load_dataframe(alerts)
    record_run = getattr(target_loader, "record_run", None)
    if callable(record_run):
        record_run(
            run_date=execution_date,
            started_at=started_at,
            finished_at=dt.datetime.now(dt.timezone.utc),
            objects_received=len(normalized),
            alerts_loaded=loaded,
            status="success",
        )
    logger.info(
        "ETL concluído para %s: %s objetos recebidos, %s alertas carregados.",
        execution_date.isoformat(),
        len(normalized),
        loaded,
    )
    return loaded
