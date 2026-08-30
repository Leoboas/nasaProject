import pandas as pd
import pytest

from etl.quality.data_contracts import (
    DataContractError,
    enforce_monitoring_contract,
    validate_monitoring_batch,
)


def _batch() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["1", "2"],
            "close_approach_date": ["2026-08-30", "2026-08-31"],
            "relative_velocity_km_s": [5.0, 7.0],
            "miss_distance_km": [100000.0, 200000.0],
            "is_potentially_hazardous_asteroid": [False, True],
            "details_json": ['{"id": "1"}', '{"id": "2"}'],
        }
    )


def test_monitoring_contract_accepts_valid_batch() -> None:
    report = validate_monitoring_batch(_batch())
    assert report.valid
    assert report.rows_checked == 2


def test_monitoring_contract_rejects_duplicate_and_null_speed() -> None:
    batch = _batch()
    batch.loc[1, "id"] = "1"
    batch.loc[1, "close_approach_date"] = "2026-08-30"
    batch.loc[1, "relative_velocity_km_s"] = None

    report = validate_monitoring_batch(batch)

    assert not report.valid
    assert report.duplicate_keys == 2
    assert report.invalid_numeric_values == 1
    with pytest.raises(DataContractError):
        enforce_monitoring_contract(batch)


def test_empty_batch_is_a_valid_noop() -> None:
    report = validate_monitoring_batch(pd.DataFrame())
    assert report.valid
    assert report.rows_checked == 0
