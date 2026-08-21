import datetime as dt
import json
import os

from etl.pipeline import run_daily_etl
from etl.transform.asteroid_transform import filter_alerts, normalize_neo_feed


def _neo(name: str, hazardous: bool = False) -> dict:
    return {
        "id": name,
        "name": name,
        "absolute_magnitude_h": 22.1,
        "is_potentially_hazardous_asteroid": hazardous,
        "estimated_diameter": {
            "kilometers": {
                "estimated_diameter_min": 0.1,
                "estimated_diameter_max": 0.2,
            }
        },
        "close_approach_data": [
            {
                "close_approach_date": "2026-08-20",
                "relative_velocity": {"kilometers_per_second": "5.0"},
                "miss_distance": {"kilometers": "12345"},
                "orbiting_body": "Earth",
            }
        ],
    }


class FakeClient:
    def fetch_neo_feed(self, start_date, end_date=None):
        return {
            "near_earth_objects": {
                start_date.isoformat(): [
                    _neo("Asteroid comum"),
                    _neo("2026 Atlas-1"),
                    _neo("3I/Example"),
                    _neo("Hazard", hazardous=True),
                ]
            }
        }


class FakeLoader:
    def __init__(self):
        self.dataframe = None

    def load_dataframe(self, dataframe):
        self.dataframe = dataframe.copy()
        return len(dataframe)


def test_filter_alerts_serializes_raw_payload():
    raw = {"near_earth_objects": {"2026-08-20": [_neo("2026 Atlas-1")]}}
    alerts = filter_alerts(normalize_neo_feed(raw))

    assert len(alerts) == 1
    assert json.loads(alerts.iloc[0]["details_json"])["name"] == "2026 Atlas-1"


def test_run_daily_etl_writes_artifacts_and_loads_only_alerts(tmp_path):
    loader = FakeLoader()
    count = run_daily_etl(
        run_date=dt.date(2026, 8, 20),
        data_dir=tmp_path,
        client=FakeClient(),
        loader=loader,
    )

    assert count == 3
    assert len(loader.dataframe) == 3
    assert (tmp_path / "samples" / "neo_raw_2026-08-20.json").exists()
    assert (tmp_path / "processed" / "neo_alertas_2026-08-20.csv").exists()


def test_run_daily_etl_removes_old_artifacts(tmp_path):
    old_raw = tmp_path / "samples" / "neo_raw_2025-01-01.json"
    old_csv = tmp_path / "processed" / "neo_alertas_2025-01-01.csv"
    old_raw.parent.mkdir(parents=True)
    old_csv.parent.mkdir(parents=True)
    old_raw.write_text("{}")
    old_csv.write_text("id")
    old_timestamp = (dt.datetime.now() - dt.timedelta(days=2)).timestamp()
    os.utime(old_raw, (old_timestamp, old_timestamp))
    os.utime(old_csv, (old_timestamp, old_timestamp))

    run_daily_etl(
        run_date=dt.date(2026, 8, 20),
        data_dir=tmp_path,
        client=FakeClient(),
        loader=FakeLoader(),
        retention_days=1,
    )

    assert not old_raw.exists()
    assert not old_csv.exists()
