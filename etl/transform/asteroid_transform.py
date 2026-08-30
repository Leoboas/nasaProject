import json
from typing import Any

import pandas as pd

from etl.common.schemas import ASTEROID_COLUMNS


def normalize_neo_feed(raw: dict[str, Any]) -> pd.DataFrame:
    """Normalize the NASA NEO feed into one row per close approach.

    Args:
        raw: JSON-decoded payload returned by the NASA NeoWS feed.

    Returns:
        A dataframe with the canonical asteroid columns and the original
        object payload in ``raw`` for auditability.
    """
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
                    "raw": asteroid,
                }
            )
    return pd.DataFrame(records, columns=ASTEROID_COLUMNS + ["raw"])


def _safe_float(value: Any) -> float | None:
    """Convert an API value to ``float`` without failing the whole batch."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def filter_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare every NEO for monitoring instead of discarding routine objects.

    Tags distinguish potentially hazardous, ATLAS, 3I and routine objects.
    Official impact probabilities still require orbital solutions such as JPL
    Sentry and are not inferred by this ETL.

    Args:
        df: Normalized dataframe produced by :func:`normalize_neo_feed`.

    Returns:
        Dataframe ready for persistence, including business alert tags.

    Raises:
        ValueError: If a non-empty batch contains an invalid approach date.
    """
    if df.empty:
        return df
    monitored = df.copy()

    # Keep the contract with PostgreSQL explicit.  NASA returns ISO-8601
    # strings, while the target schema uses a DATE primary-key component.
    monitored["close_approach_date"] = pd.to_datetime(
        monitored["close_approach_date"], errors="coerce"
    ).dt.date
    if monitored["close_approach_date"].isna().any():
        raise ValueError("close_approach_date contem valor invalido")

    def _tag(row):
        name = str(row.get("name", "")).lower()
        tags = []
        if row.get("is_potentially_hazardous_asteroid"):
            tags.append("hazard")
        if "atlas" in name:
            tags.append("atlas")
        if name.startswith("3i"):
            tags.append("3i")
        return ",".join(tags) if tags else "routine"

    monitored["alert_tag"] = monitored.apply(_tag, axis=1)
    monitored["details_json"] = monitored["raw"].apply(
        lambda value: json.dumps(value, ensure_ascii=False, default=str)
    )
    keep_cols = [
        "id",
        "name",
        "close_approach_date",
        "absolute_magnitude_h",
        "relative_velocity_km_s",
        "miss_distance_km",
        "alert_tag",
        "is_potentially_hazardous_asteroid",
        "details_json",
    ]
    return monitored[keep_cols]
