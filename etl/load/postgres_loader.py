import pandas as pd
from sqlalchemy import create_engine

from etl.common.config import pg_config
from etl.common.logging_config import get_logger

logger = get_logger(__name__)


class PostgresLoader:
    """Loader simples para Postgres usando SQLAlchemy."""

    def __init__(self, table_name: str = "neo_asteroids", if_exists: str = "append"):
        self.table_name = table_name
        self.if_exists = if_exists
        self.engine = create_engine(pg_config.sql_alchemy_uri)

    def load_dataframe(self, df: pd.DataFrame) -> int:
        if df.empty:
            logger.warning("DataFrame vazio; nada a carregar.")
            return 0
        logger.info("Carregando %s registros em %s", len(df), self.table_name)
        df.to_sql(self.table_name, self.engine, if_exists=self.if_exists, index=False)
        return len(df)
