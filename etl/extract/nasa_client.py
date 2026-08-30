from __future__ import annotations

import datetime as dt
from typing import Any

import requests

from etl.common.config import get_nasa_config
from etl.common.logging_config import get_logger


logger = get_logger(__name__)


class NASAClient:
    """Cliente HTTP para o endpoint NASA NeoWS Feed."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        resource: str | None = None,
    ) -> None:
        config = get_nasa_config()
        self.api_key = api_key or config.api_key
        self.base_url = (base_url or config.base_url).rstrip("/")
        self.resource = (resource or config.resource).lstrip("/")

    def fetch_neo_feed(self, start_date: dt.date, end_date: dt.date | None = None) -> dict[str, Any]:
        """Fetch a bounded date range from the NASA NEO Feed.

        Args:
            start_date: First date included in the NASA request.
            end_date: Last date included; defaults to ``start_date``.

        Returns:
            The decoded JSON payload returned by NASA.

        Raises:
            requests.RequestException: If the request fails or times out.
            ValueError: If NASA returns invalid JSON.
        """
        end = end_date or start_date
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end.isoformat(),
            "api_key": self.api_key,
        }
        logger.info("Consultando NASA NEO Feed %s - %s", params["start_date"], params["end_date"])
        response = requests.get(f"{self.base_url}/{self.resource}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
