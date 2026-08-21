import pandas as pd
import pytest

from etl.load.postgres_loader import MONITORING_TABLE, PostgresLoader


def test_loader_rejects_legacy_table_before_connecting() -> None:
    with pytest.raises(ValueError, match="asteroides_monitoria"):
        PostgresLoader(table_name="neo_asteroids")


def test_loader_returns_zero_for_empty_dataframe_without_connection() -> None:
    loader = PostgresLoader.__new__(PostgresLoader)
    loader.table_name = MONITORING_TABLE
    assert loader.load_dataframe(pd.DataFrame()) == 0
