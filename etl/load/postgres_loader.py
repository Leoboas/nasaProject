import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy import text

from etl.common.config import pg_config
from etl.common.logging_config import get_logger

logger = get_logger(__name__)


class PostgresLoader:
    """Loader simples para Postgres usando SQLAlchemy."""

    def __init__(self, table_name: str = "neo_asteroids", if_exists: str = "append"):
        self.table_name = table_name
        self.if_exists = if_exists
        self.engine = create_engine(pg_config.sql_alchemy_uri)
        self._ensure_table()

    def _ensure_table(self):
        if self.table_name != "asteroides_monitoria":
            return
        ddl = """
        CREATE TABLE IF NOT EXISTS asteroides_monitoria (
            id TEXT NOT NULL,
            name TEXT,
            close_approach_date DATE,
            absolute_magnitude_h DOUBLE PRECISION,
            relative_velocity_km_s DOUBLE PRECISION,
            miss_distance_km DOUBLE PRECISION,
            alert_tag TEXT,
            is_potentially_hazardous_asteroid BOOLEAN,
            details_json JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (id, close_approach_date)
        );
        """
        cleanup = """
        DELETE FROM asteroides_monitoria
        WHERE close_approach_date < CURRENT_DATE - INTERVAL '90 days';
        """
        with self.engine.begin() as conn:
            conn.execute(text(ddl))
            conn.execute(text(cleanup))

    def load_dataframe(self, df: pd.DataFrame) -> int:
        if df.empty:
            logger.warning("DataFrame vazio; nada a carregar.")
            return 0
        logger.info("Carregando %s registros em %s", len(df), self.table_name)
        if self.table_name == "asteroides_monitoria":
            return self._upsert_monitoria(df)
        df.to_sql(self.table_name, self.engine, if_exists=self.if_exists, index=False)
        return len(df)

    def _upsert_monitoria(self, df: pd.DataFrame) -> int:
        # upsert baseado em (id, close_approach_date)
        rows = df.to_dict(orient="records")
        stmt = text(
            """
            INSERT INTO asteroides_monitoria (
                id, name, close_approach_date, absolute_magnitude_h,
                relative_velocity_km_s, miss_distance_km, alert_tag,
                is_potentially_hazardous_asteroid, details_json
            )
            VALUES (
                :id, :name, :close_approach_date, :absolute_magnitude_h,
                :relative_velocity_km_s, :miss_distance_km, :alert_tag,
                :is_potentially_hazardous_asteroid, :details_json
            )
            ON CONFLICT (id, close_approach_date) DO UPDATE
            SET
                name = EXCLUDED.name,
                absolute_magnitude_h = EXCLUDED.absolute_magnitude_h,
                relative_velocity_km_s = EXCLUDED.relative_velocity_km_s,
                miss_distance_km = EXCLUDED.miss_distance_km,
                alert_tag = EXCLUDED.alert_tag,
                is_potentially_hazardous_asteroid = EXCLUDED.is_potentially_hazardous_asteroid,
                details_json = EXCLUDED.details_json
            """
        )
        with self.engine.begin() as conn:
            conn.execute(stmt, rows)
        return len(df)
