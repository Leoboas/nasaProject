import datetime as dt
import requests

from etl.common.config import nasa_config
from etl.common.logging_config import get_logger

logger = get_logger(__name__)


class NASAClient:
    """Cliente simples para NASA NEO Feed."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or nasa_config.api_key
        self.base_url = nasa_config.base_url
        self.resource = nasa_config.resource

    def fetch_neo_feed(self, start_date: dt.date, end_date: dt.date | None = None) -> dict:
        end = end_date or start_date
        url = f"{self.base_url}/{self.resource}"
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end.isoformat(),
            "api_key": self.api_key,
        }
        logger.info("Consultando NASA NEO Feed %s - %s", params["start_date"], params["end_date"])
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
