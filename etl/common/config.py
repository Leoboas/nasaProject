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
class AWSConfig:
    access_key: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    secret_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    region: str = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    s3_bucket: str = os.getenv("AWS_BUCKET_NAME", os.getenv("S3_BUCKET", "nasa-etl-demo"))


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
aws_config = AWSConfig()
pg_config = PostgresConfig()
