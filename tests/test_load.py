import os

import pytest
import pandas as pd

from etl.load.postgres_loader import PostgresLoader


@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="Defina RUN_POSTGRES_INTEGRATION=1 para executar contra um PostgreSQL isolado.",
)
def test_loader_with_empty_df():
    loader = PostgresLoader(table_name="neo_asteroids_test")
    df = pd.DataFrame()
    count = loader.load_dataframe(df)
    assert count == 0
