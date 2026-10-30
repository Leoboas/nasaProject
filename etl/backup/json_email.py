"""Create portable PostgreSQL JSON backups and deliver them over SMTP."""

from __future__ import annotations

import gzip
import json
import os
import smtplib
import ssl
from datetime import date, datetime, timezone
from email.message import EmailMessage
from typing import Any, Mapping

from sqlalchemy import Engine, text


BACKUP_TABLES: dict[str, tuple[str, ...]] = {
    "asteroides_monitoria": (
        "id",
        "name",
        "close_approach_date",
        "absolute_magnitude_h",
        "relative_velocity_km_s",
        "miss_distance_km",
        "alert_tag",
        "is_potentially_hazardous_asteroid",
        "details_json",
        "created_at",
    ),
    "etl_runs": (
        "id",
        "run_date",
        "started_at",
        "finished_at",
        "objects_received",
        "alerts_loaded",
        "status",
        "error_message",
    ),
}


def validate_email_config() -> None:
    """Fail before export/upload when required SMTP settings are incomplete."""
    required = ("BACKUP_EMAIL_TO", "SMTP_HOST", "SMTP_FROM")
    missing = [key for key in required if not os.getenv(key, "").strip()]
    if missing:
        raise ValueError(f"Configuração de e-mail ausente: {', '.join(missing)}")
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if bool(username) != bool(password):
        raise ValueError("SMTP_USERNAME e SMTP_PASSWORD devem ser definidos juntos")
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        max_size_mb = float(os.getenv("BACKUP_EMAIL_MAX_ATTACHMENT_MB", "15"))
    except ValueError as exc:
        raise ValueError("SMTP_PORT e limite de anexo devem ser valores numéricos") from exc
    if not 1 <= port <= 65535:
        raise ValueError("SMTP_PORT deve estar entre 1 e 65535")
    if max_size_mb <= 0:
        raise ValueError("BACKUP_EMAIL_MAX_ATTACHMENT_MB deve ser maior que zero")


def _json_default(value: Any) -> str:
    """Serialize common PostgreSQL date/time and decimal values as strings."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def create_backup_archive(engine: Engine) -> bytes:
    """Read project tables and return a deterministic gzip-compressed JSON.

    Args:
        engine: SQLAlchemy engine connected to the local ``nasa_etl`` database.

    Returns:
        Gzip bytes containing a versioned document with rows from both tables.

    Raises:
        sqlalchemy.exc.SQLAlchemyError: If a table cannot be queried.
    """
    tables: dict[str, list[Mapping[str, Any]]] = {}
    with engine.connect() as connection:
        for table_name, columns in BACKUP_TABLES.items():
            selected = ", ".join(f'"{column}"' for column in columns)
            rows = connection.execute(
                text(f'SELECT {selected} FROM public."{table_name}" ORDER BY 1')
            ).mappings()
            tables[table_name] = [dict(row) for row in rows]

    document = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database": os.getenv("POSTGRES_DB", "nasa_etl"),
        "tables": tables,
    }
    json_bytes = json.dumps(
        document,
        ensure_ascii=False,
        default=_json_default,
        separators=(",", ":"),
    ).encode("utf-8")
    return gzip.compress(json_bytes, compresslevel=6, mtime=0)


def send_backup_email(
    archive: bytes,
    *,
    object_uri: str,
    download_url: str,
    created_at: datetime,
) -> str:
    """Email a backup attachment, or a time-limited S3 link when oversized.

    SMTP settings and recipient are read from environment variables. The
    function never logs or returns SMTP credentials.

    Returns:
        ``attachment`` when the gzip JSON was attached, otherwise ``link``.

    Raises:
        ValueError: If required SMTP settings are absent or inconsistent.
        OSError: If the SMTP connection or delivery fails.
    """
    validate_email_config()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")

    recipient = os.environ["BACKUP_EMAIL_TO"].strip()
    sender = os.environ["SMTP_FROM"].strip()
    max_size_mb = float(os.getenv("BACKUP_EMAIL_MAX_ATTACHMENT_MB", "15"))
    message = EmailMessage()
    message["Subject"] = f"NASA ETL | backup semanal | {created_at:%Y-%m-%d}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "Backup semanal do banco nasa_etl.\n"
        f"Gerado em: {created_at.isoformat()}\n"
        f"Objeto no S3: {object_uri}\n"
        + (f"Download temporario: {download_url}\n" if len(archive) > max_size_mb * 1024**2 else "")
        + "Formato: JSON UTF-8 comprimido com gzip."
    )

    if len(archive) <= max_size_mb * 1024**2:
        message.add_attachment(
            archive,
            maintype="application",
            subtype="gzip",
            filename=f"nasa-etl-{created_at:%Y%m%dT%H%M%SZ}.json.gz",
        )

    host = os.environ["SMTP_HOST"].strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes"}
    context = ssl.create_default_context()
    smtp_factory = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_factory(host, port, timeout=30, context=context) if use_ssl else smtp_factory(
        host, port, timeout=30
    ) as server:
        if not use_ssl:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(message)

    return "attachment" if len(archive) <= max_size_mb * 1024**2 else "link"
