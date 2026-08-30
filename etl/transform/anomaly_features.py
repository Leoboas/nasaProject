"""Feature engineering shared by the monitoring dashboard and ETL reports."""

from __future__ import annotations

import numpy as np
import pandas as pd

ANOMALY_FEATURE_COLUMNS = (
    "velocity_log",
    "mass_log",
    "miss_distance_au_log",
    "diameter_velocity_ratio",
)


def build_anomaly_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Create numerically stable features for Isolation Forest.

    Args:
        dataframe: Feature-enriched monitoring rows. Missing columns are
            treated as null so callers can decide whether to skip the model.

    Returns:
        A copy with log-scaled magnitude features and the diameter-to-speed
        ratio in metres per km/h. The input dataframe is never mutated.
    """

    result = dataframe.copy()
    def _numeric_series(column: str) -> pd.Series:
        if column not in result:
            return pd.Series(np.nan, index=result.index, dtype="float64")
        return pd.to_numeric(result[column], errors="coerce")

    numeric = {
        column: _numeric_series(column)
        for column in ("velocity_kmh", "mass_kg", "miss_distance_au", "diameter_m")
    }
    velocity = numeric["velocity_kmh"].clip(lower=0)
    result["velocity_log"] = np.log1p(velocity)
    result["mass_log"] = np.log1p(numeric["mass_kg"].clip(lower=0))
    result["miss_distance_au_log"] = np.log1p(numeric["miss_distance_au"].clip(lower=0))
    result["diameter_velocity_ratio"] = numeric["diameter_m"] / velocity.clip(lower=1.0)
    result.replace([np.inf, -np.inf], np.nan, inplace=True)
    return result
