import os

import pytest
import pandas as pd

from etl.load.postgres_loader import PostgresLoader


@pytest.mark.skipif(
    os.getenv("POSTGRES_HOST") is None, reason="Requer Postgres configurado via env vars."
)
def test_loader_with_empty_df():
    loader = PostgresLoader(table_name="neo_asteroids_test")
    df = pd.DataFrame()
    count = loader.load_dataframe(df)
    assert count == 0
