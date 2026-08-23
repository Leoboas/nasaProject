from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from etl.common.config import get_postgres_config
from etl.common.logging_config import get_logger


logger = get_logger(__name__)
MONITORING_TABLE = "asteroides_monitoria"


class PostgresLoader:
    """Persiste alertas monitorados com UPSERT idempotente no PostgreSQL."""

    def __init__(self, table_name: str = MONITORING_TABLE) -> None:
        if table_name != MONITORING_TABLE:
            raise ValueError(f"A tabela suportada é somente {MONITORING_TABLE!r}.")

        self.table_name = table_name
        self.engine: Engine = create_engine(
            get_postgres_config().sqlalchemy_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )

    def load_dataframe(self, dataframe: pd.DataFrame) -> int:
        if dataframe.empty:
            logger.info("DataFrame vazio; nada a carregar.")
            return 0

        logger.info("Carregando %s registros em %s", len(dataframe), self.table_name)
        rows = dataframe.to_dict(orient="records")
        statement = text(
            """
            INSERT INTO asteroides_monitoria (
                id, name, close_approach_date, absolute_magnitude_h,
                relative_velocity_km_s, miss_distance_km, alert_tag,
                is_potentially_hazardous_asteroid, details_json
            )
            VALUES (
                :id, :name, :close_approach_date, :absolute_magnitude_h,
                :relative_velocity_km_s, :miss_distance_km, :alert_tag,
                :is_potentially_hazardous_asteroid, CAST(:details_json AS JSONB)
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
        with self.engine.begin() as connection:
            connection.execute(statement, rows)
        return len(dataframe)

    def record_run(
        self,
        *,
        run_date,
        started_at,
        finished_at,
        objects_received: int,
        alerts_loaded: int,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Persist a heartbeat even when the daily filter loads zero rows."""

        ddl = text(
            """
            CREATE TABLE IF NOT EXISTS etl_runs (
                id BIGSERIAL PRIMARY KEY,
                run_date DATE NOT NULL,
                started_at TIMESTAMPTZ NOT NULL,
                finished_at TIMESTAMPTZ NOT NULL,
                objects_received INTEGER NOT NULL DEFAULT 0,
                alerts_loaded INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT
            )
            """
        )
        statement = text(
            """
            INSERT INTO etl_runs (
                run_date, started_at, finished_at, objects_received,
                alerts_loaded, status, error_message
            ) VALUES (
                :run_date, :started_at, :finished_at, :objects_received,
                :alerts_loaded, :status, :error_message
            )
            """
        )
        with self.engine.begin() as connection:
            connection.execute(ddl)
            connection.execute(
                statement,
                {
                    "run_date": run_date,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "objects_received": objects_received,
                    "alerts_loaded": alerts_loaded,
                    "status": status,
                    "error_message": error_message,
                },
            )
