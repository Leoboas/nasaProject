"""Helpers for communicating official CNEOS Torino assessments."""

from __future__ import annotations

import logging

import pandas as pd

LOGGER = logging.getLogger(__name__)


def find_torino_alerts(
    dataframe: pd.DataFrame,
    *,
    score_column: str = "ts_max",
    threshold: float = 1.0,
) -> pd.DataFrame:
    """Return rows whose authoritative Torino score exceeds a threshold.

    Args:
        dataframe: Rows returned by CNEOS Sentry or another official source.
        score_column: Column containing the official numeric Torino score.
        threshold: Exclusive lower bound for a business alert.

    Returns:
        A copy containing only rows with numeric score greater than threshold.
        An absent score column produces an empty dataframe rather than an
        inferred or fabricated risk value.
    """

    if dataframe.empty or score_column not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    scores = pd.to_numeric(dataframe[score_column], errors="coerce")
    return dataframe.loc[scores.gt(threshold)].copy()


def emit_torino_alerts(dataframe: pd.DataFrame) -> int:
    """Log critical alerts for official Torino scores above one.

    Args:
        dataframe: Official Sentry rows containing ``ts_max``.

    Returns:
        Number of critical rows emitted to the application logger.
    """

    alerts = find_torino_alerts(dataframe)
    for _, row in alerts.iterrows():
        designation = row.get("des", row.get("fullname", "unknown"))
        score = row.get("ts_max")
        LOGGER.warning(
            "ALERTA CRÍTICO: objeto %s possui Escala de Torino oficial %s (> 1).",
            designation,
            score,
        )
    return len(alerts)
