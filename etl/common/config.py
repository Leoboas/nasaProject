"""Configuração tipada do pipeline, carregada no momento de uso."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from sqlalchemy.engine import URL


load_dotenv(override=False)


@dataclass(frozen=True)
class NASAConfig:
    api_key: str
    base_url: str
    resource: str


@dataclass(frozen=True)
class PostgresConfig:
    user: str
    password: str
    database: str
    host: str
    port: int

    @property
    def sqlalchemy_url(self) -> URL:
        """Monta a URL sem interpolar senha em uma string."""

        return URL.create(
            "postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )


def get_nasa_config() -> NASAConfig:
    return NASAConfig(
        api_key=os.getenv("NASA_API_KEY", "DEMO_KEY"),
        base_url=os.getenv("NASA_API_BASE", "https://api.nasa.gov").rstrip("/"),
        resource=os.getenv("NASA_API_RESOURCE", "neo/rest/v1/feed").lstrip("/"),
    )


def get_postgres_config() -> PostgresConfig:
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "POSTGRES_HOST")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Variáveis PostgreSQL ausentes: {', '.join(missing)}")

    port_value = os.getenv("POSTGRES_PORT", "5432")
    try:
        port = int(port_value)
    except ValueError as exc:
        raise RuntimeError("POSTGRES_PORT deve ser um número inteiro válido.") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("POSTGRES_PORT deve estar entre 1 e 65535.")

    return PostgresConfig(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        database=os.environ["POSTGRES_DB"],
        host=os.environ["POSTGRES_HOST"],
        port=port,
    )
