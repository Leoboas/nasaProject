
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from airflow.models import BaseOperator
from airflow.utils.context import Context

from etl.common.logging_config import get_logger
from plugins.hooks.nasa_api_hook import NASAApiHook

logger = get_logger(__name__)


class NASAExtractOperator(BaseOperator):
    """Extrai dados da NASA API e grava JSON bruto em disco, retornando o caminho."""

    template_fields = ("output_path", "start_date", "end_date")

    def __init__(
        self,
        output_path: str = "/opt/airflow/data/samples/neo_raw_{{ ds }}.json",
        http_conn_id: str | None = None,
        start_date: dt.date | None = None,
        end_date: dt.date | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.output_path = output_path
        self.http_conn_id = http_conn_id
        self.start_date = start_date
        self.end_date = end_date

    def execute(self, context: Context) -> str:
        exec_date: dt.datetime = context["execution_date"]
        start = self.start_date or exec_date.date()
        end = self.end_date or start
        hook = NASAApiHook(http_conn_id=self.http_conn_id)
        data = hook.get_neo_feed(start_date=start, end_date=end)

        path = Path(self.output_path.format(**context))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        logger.info("Payload NASA salvo em %s", path)
        return str(path)
