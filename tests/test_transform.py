from etl.transform.asteroid_transform import normalize_neo_feed
from etl.common.schemas import ASTEROID_COLUMNS


def test_normalize_neo_feed():
    raw = {
        "near_earth_objects": {
            "2023-10-01": [
                {
                    "id": "1",
                    "name": "Asteroid 1",
                    "absolute_magnitude_h": 22.1,
                    "is_potentially_hazardous_asteroid": True,
                    "estimated_diameter": {
                        "kilometers": {
                            "estimated_diameter_min": 0.1,
                            "estimated_diameter_max": 0.2,
                        }
                    },
                    "close_approach_data": [
                        {
                            "close_approach_date": "2023-10-01",
                            "relative_velocity": {"kilometers_per_second": "5.0"},
                            "miss_distance": {"kilometers": "12345"},
                            "orbiting_body": "Earth",
                        }
                    ],
                }
            ]
        }
    }
    df = normalize_neo_feed(raw)
    assert list(df.columns) == ASTEROID_COLUMNS + ["raw"]
    assert len(df) == 1
