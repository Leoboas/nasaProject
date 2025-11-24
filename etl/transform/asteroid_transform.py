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
                    "raw": asteroid,
                }
            )
    df = pd.DataFrame(records, columns=ASTEROID_COLUMNS + ["raw"])
    return df


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def filter_alerts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Mantém somente asteroides relevantes:
    - potencialmente perigosos
    - ou nome contendo 'atlas'
    - ou nome iniciando com '3i'
    Adiciona tag de alerta e serializa detalhes.
    """
    if df.empty:
        return df
    mask_hazard = df["is_potentially_hazardous_asteroid"].fillna(False)
    mask_atlas = df["name"].fillna("").str.lower().str.contains("atlas")
    mask_3i = df["name"].fillna("").str.lower().str.startswith("3i")
    filtered = df[mask_hazard | mask_atlas | mask_3i].copy()
    if filtered.empty:
        return filtered

    def _tag(row):
        name = str(row.get("name", "")).lower()
        tags = []
        if row.get("is_potentially_hazardous_asteroid"):
            tags.append("hazard")
        if "atlas" in name:
            tags.append("atlas")
        if name.startswith("3i"):
            tags.append("3i")
        return ",".join(tags) if tags else "other"

    filtered["alert_tag"] = filtered.apply(_tag, axis=1)
    filtered["details_json"] = filtered["raw"].apply(lambda x: pd.io.json.dumps(x))
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
    return filtered[keep_cols]
