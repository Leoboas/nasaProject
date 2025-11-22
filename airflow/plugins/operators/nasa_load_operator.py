from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from airflow.models import BaseOperator
from airflow.utils.context import Context

from etl.common.logging_config import get_logger
from etl.load.postgres_loader import PostgresLoader

logger = get_logger(__name__)


class NASALoadOperator(BaseOperator):
    """Carrega CSV transformado no Postgres."""

    template_fields = ("input_path",)

    def __init__(self, input_path: str, table_name: str = "neo_asteroids", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.input_path = input_path
        self.table_name = table_name

    def execute(self, context: Context) -> int:
        path = Path(self.input_path.format(**context))
        df = pd.read_csv(path)
        loader = PostgresLoader(table_name=self.table_name)
        count = loader.load_dataframe(df)
        logger.info("Carga finalizada: %s registros", count)
        return count
