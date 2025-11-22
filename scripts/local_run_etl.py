import datetime as dt
import json
from pathlib import Path

from etl.extract.nasa_client import NASAClient
from etl.transform.asteroid_transform import normalize_neo_feed
from etl.load.postgres_loader import PostgresLoader


def main():
    today = dt.date.today()
    client = NASAClient()
    raw = client.fetch_neo_feed(start_date=today)

    raw_path = Path("data/samples/neo_raw_local.json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(raw))

    df = normalize_neo_feed(raw)
    csv_path = Path("data/processed/neo_local.csv")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)

    loader = PostgresLoader()
    loader.load_dataframe(df)
    print(f"ETL local concluído. Registros: {len(df)}")


if __name__ == "__main__":
    main()
