import pytest

from etl.common.config import PostgresConfig, get_postgres_config


def test_postgres_url_encodes_reserved_password_characters() -> None:
    config = PostgresConfig(
        user="nasa_app",
        password="p@ss:word/with space",
        database="nasa_etl",
        host="localhost",
        port=5432,
    )

    rendered = config.sqlalchemy_url.render_as_string(hide_password=False)

    assert "p%40ss%3Aword%2Fwith space" in rendered


def test_postgres_config_requires_all_connection_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="POSTGRES_USER"):
        get_postgres_config()
