from __future__ import annotations

import datetime as dt
import json
from typing import Any

from airflow.hooks.base import BaseHook
from airflow.providers.http.hooks.http import HttpHook

from etl.common.config import nasa_config


class NASAApiHook(BaseHook):
    """Hook para NASA NEO Feed utilizando HttpHook do Airflow."""

    conn_name_attr = "http_conn_id"
    default_conn_name = "nasa_api"
    hook_name = "NASA API"

    def __init__(self, http_conn_id: str | None = None) -> None:
        super().__init__()
        self.http_conn_id = http_conn_id or self.default_conn_name
        self.http_hook = HttpHook(method="GET", http_conn_id=self.http_conn_id)

    def get_neo_feed(self, start_date: dt.date, end_date: dt.date | None = None) -> dict[str, Any]:
        end = end_date or start_date
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end.isoformat(),
            "api_key": nasa_config.api_key,
        }
        resp = self.http_hook.run(
            endpoint=nasa_config.resource,
            data=params,
        )
        resp.raise_for_status()
        return json.loads(resp.text)
