from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from airflow.models import BaseOperator
from airflow.utils.context import Context

from etl.common.logging_config import get_logger
from etl.transform.asteroid_transform import normalize_neo_feed

logger = get_logger(__name__)


class NASATransformOperator(BaseOperator):
    """Transforma JSON bruto em CSV normalizado, retornando o caminho do CSV."""

    template_fields = ("input_path", "output_path")

    def __init__(
        self,
        input_path: str,
        output_path: str = "/opt/airflow/data/processed/neo_{{ ds }}.csv",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.input_path = input_path
        self.output_path = output_path

    def execute(self, context: Context) -> str:
        in_path = Path(self.input_path.format(**context))
        out_path = Path(self.output_path.format(**context))
        out_path.parent.mkdir(parents=True, exist_ok=True)

        raw = json.loads(in_path.read_text())
        df = normalize_neo_feed(raw)
        df.to_csv(out_path, index=False)
        logger.info("Transformação concluída: %s linhas -> %s", len(df), out_path)
        return str(out_path)
