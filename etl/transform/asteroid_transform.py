import pandas as pd

from etl.common.schemas import ASTEROID_COLUMNS


def normalize_neo_feed(raw: dict) -> pd.DataFrame:
    """Normaliza o feed NEO da NASA em um DataFrame plano."""
    records = []
    neo_data = raw.get("near_earth_objects", {})
    for date_str, asteroids in neo_data.items():
        for asteroid in asteroids:
            approach = asteroid.get("close_approach_data", [{}])[0]
            diameter = asteroid.get("estimated_diameter", {}).get("kilometers", {})
            records.append(
                {
                    "id": asteroid.get("id"),
                    "name": asteroid.get("name"),
                    "absolute_magnitude_h": asteroid.get("absolute_magnitude_h"),
                    "is_potentially_hazardous_asteroid": asteroid.get(
                        "is_potentially_hazardous_asteroid", False
                    ),
                    "estimated_diameter_min_km": diameter.get("estimated_diameter_min"),
                    "estimated_diameter_max_km": diameter.get("estimated_diameter_max"),
                    "close_approach_date": approach.get("close_approach_date", date_str),
                    "relative_velocity_km_s": _safe_float(
                        approach.get("relative_velocity", {}).get("kilometers_per_second")
                    ),
                    "miss_distance_km": _safe_float(
                        approach.get("miss_distance", {}).get("kilometers")
                    ),
                    "orbiting_body": approach.get("orbiting_body"),
                }
            )
    df = pd.DataFrame(records, columns=ASTEROID_COLUMNS)
    return df


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
