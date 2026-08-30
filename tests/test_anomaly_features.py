import numpy as np
import pandas as pd

from etl.transform.anomaly_features import ANOMALY_FEATURE_COLUMNS, build_anomaly_features


def test_anomaly_features_include_diameter_velocity_ratio() -> None:
    frame = pd.DataFrame(
        {"velocity_kmh": [36000.0], "mass_kg": [1000.0], "miss_distance_au": [0.1], "diameter_m": [20.0]}
    )

    result = build_anomaly_features(frame)

    assert set(ANOMALY_FEATURE_COLUMNS).issubset(result.columns)
    assert result.loc[0, "diameter_velocity_ratio"] == 20.0 / 36000.0
    assert np.isfinite(result.loc[0, "velocity_log"])
    assert frame.columns.tolist() == ["velocity_kmh", "mass_kg", "miss_distance_au", "diameter_m"]


def test_missing_feature_columns_are_null_instead_of_raising() -> None:
    result = build_anomaly_features(pd.DataFrame({"velocity_kmh": [10.0]}))
    assert result["diameter_velocity_ratio"].isna().all()
