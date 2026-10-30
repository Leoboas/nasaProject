import gzip
import json
import smtplib
from datetime import date, datetime, timezone

import pytest

from etl.backup.json_email import create_backup_archive, send_backup_email


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class _FakeConnection:
    def __init__(self):
        self.query_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, _query):
        self.query_count += 1
        if self.query_count == 1:
            return _FakeResult(
                [{"id": "42", "close_approach_date": date(2026, 10, 30)}]
            )
        return _FakeResult([{"id": 3, "finished_at": datetime(2026, 10, 30, tzinfo=timezone.utc)}])


class _FakeEngine:
    def connect(self):
        return _FakeConnection()


def test_backup_archive_is_versioned_gzip_json():
    archive = create_backup_archive(_FakeEngine())
    document = json.loads(gzip.decompress(archive))

    assert document["schema_version"] == 1
    assert document["tables"]["asteroides_monitoria"][0]["close_approach_date"] == "2026-10-30"
    assert document["tables"]["etl_runs"][0]["id"] == 3


def test_email_requires_destination_and_transport_settings(monkeypatch):
    monkeypatch.delenv("BACKUP_EMAIL_TO", raising=False)
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)

    with pytest.raises(ValueError, match="BACKUP_EMAIL_TO"):
        send_backup_email(
            b"{}",
            object_uri="s3://bucket/key",
            download_url="https://example.invalid/",
            created_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
        )


class _FakeSMTP:
    message = None

    def __init__(self, *_args, **_kwargs):
        self.starttls_called = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def ehlo(self):
        pass

    def starttls(self, **_kwargs):
        self.starttls_called = True

    def login(self, *_args):
        pass

    def send_message(self, message):
        type(self).message = message


def test_email_attaches_small_backup_over_starttls(monkeypatch):
    monkeypatch.setenv("BACKUP_EMAIL_TO", "recruiter@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "nasa-etl@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "nasa-etl@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setenv("BACKUP_EMAIL_MAX_ATTACHMENT_MB", "15")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    result = send_backup_email(
        b"compressed-json",
        object_uri="s3://private-bucket/bronze/backups/file.json.gz",
        download_url="https://example.invalid/temporary",
        created_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )

    assert result == "attachment"
    parts = _FakeSMTP.message.iter_attachments()
    assert next(parts).get_filename().endswith(".json.gz")


def test_email_uses_link_when_archive_exceeds_configured_limit(monkeypatch):
    monkeypatch.setenv("BACKUP_EMAIL_TO", "recruiter@example.com")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "nasa-etl@example.com")
    monkeypatch.setenv("SMTP_USERNAME", "")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("SMTP_USE_SSL", "false")
    monkeypatch.setenv("BACKUP_EMAIL_MAX_ATTACHMENT_MB", "0.000001")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    result = send_backup_email(
        b"compressed-json",
        object_uri="s3://private-bucket/bronze/backups/file.json.gz",
        download_url="https://example.invalid/temporary",
        created_at=datetime(2026, 10, 30, tzinfo=timezone.utc),
    )

    assert result == "link"
    assert "https://example.invalid/temporary" in _FakeSMTP.message.get_content()
    assert list(_FakeSMTP.message.iter_attachments()) == []
