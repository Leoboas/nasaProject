import pandas as pd

from etl.risk.torino import find_torino_alerts


def test_find_torino_alerts_uses_exclusive_threshold() -> None:
    frame = pd.DataFrame({"des": ["A", "B", "C"], "ts_max": [0, 1, 2]})
    alerts = find_torino_alerts(frame)
    assert alerts["des"].tolist() == ["C"]


def test_find_torino_alerts_does_not_infer_missing_official_column() -> None:
    frame = pd.DataFrame({"des": ["A"], "torino_scale_proxy": [10]})
    assert find_torino_alerts(frame).empty
