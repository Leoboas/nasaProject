import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env quando presente
load_dotenv()


@dataclass
class NASAConfig:
    api_key: str = os.getenv("NASA_API_KEY", "DEMO_KEY")
    base_url: str = os.getenv("NASA_API_BASE", "https://api.nasa.gov")
    resource: str = os.getenv("NASA_API_RESOURCE", "neo/rest/v1/feed")


@dataclass
class PostgresConfig:
    user: str = os.getenv("POSTGRES_USER", "airflow")
    password: str = os.getenv("POSTGRES_PASSWORD", "airflow")
    db: str = os.getenv("POSTGRES_DB", "airflow")
    host: str = os.getenv("POSTGRES_HOST", "postgres")
    port: int = int(os.getenv("POSTGRES_PORT", "5432"))

    @property
    def sql_alchemy_uri(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


nasa_config = NASAConfig()
pg_config = PostgresConfig()
