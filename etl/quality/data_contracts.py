"""Assertions for the dataframe contract shared by Silver and Gold layers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

REQUIRED_COLUMNS = (
    "id",
    "close_approach_date",
    "relative_velocity_km_s",
    "miss_distance_km",
    "is_potentially_hazardous_asteroid",
    "details_json",
)
NUMERIC_COLUMNS = ("relative_velocity_km_s", "miss_distance_km")


@dataclass(frozen=True)
class DataQualityReport:
    """Summary of contract violations found in one transformed batch."""

    valid: bool
    rows_checked: int
    duplicate_keys: int
    null_ids: int
    invalid_dates: int
    invalid_numeric_values: int
    invalid_json_values: int
    violations: tuple[str, ...] = ()


class DataContractError(ValueError):
    """Raised when a batch cannot be safely persisted."""

    def __init__(self, report: DataQualityReport) -> None:
        self.report = report
        super().__init__("Contrato de dados inválido: " + "; ".join(report.violations))


def _as_violations(values: Iterable[str]) -> tuple[str, ...]:
    """Return non-empty violation messages as an immutable tuple."""

    return tuple(value for value in values if value)


def validate_monitoring_batch(dataframe: pd.DataFrame) -> DataQualityReport:
    """Validate canonical asteroid rows without mutating the dataframe.

    Args:
        dataframe: Dataframe produced by the transformation layer.

    Returns:
        A report containing counts and human-readable contract violations.
        Invalid batches are logged at warning level for operational triage.
    """

    rows_checked = len(dataframe)
    if dataframe.empty:
        return DataQualityReport(valid=True, rows_checked=0, duplicate_keys=0,
                                 null_ids=0, invalid_dates=0,
                                 invalid_numeric_values=0, invalid_json_values=0)

    violations: list[str] = []
    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        violations.append(f"colunas ausentes: {', '.join(missing)}")
        report = DataQualityReport(
            valid=False,
            rows_checked=rows_checked,
            duplicate_keys=0,
            null_ids=0,
            invalid_dates=0,
            invalid_numeric_values=0,
            invalid_json_values=0,
            violations=tuple(violations),
        )
        LOGGER.warning("Data contract rejeitou lote: %s", "; ".join(report.violations))
        return report

    ids = dataframe["id"].astype("string")
    null_ids = int(ids.isna().sum() + ids.str.strip().eq("").sum())
    if null_ids:
        violations.append(f"{null_ids} ID(s) nulo(s) ou vazio(s)")

    dates = pd.to_datetime(dataframe["close_approach_date"], errors="coerce")
    invalid_dates = int(dates.isna().sum())
    if invalid_dates:
        violations.append(f"{invalid_dates} data(s) de aproximação inválida(s)")

    invalid_numeric_values = 0
    for column in NUMERIC_COLUMNS:
        numeric = pd.to_numeric(dataframe[column], errors="coerce")
        invalid = numeric.isna() | ~np.isfinite(numeric)
        if column == "relative_velocity_km_s":
            invalid = invalid | numeric.lt(0)
        else:
            invalid = invalid | numeric.lt(0)
        count = int(invalid.sum())
        invalid_numeric_values += count
        if count:
            violations.append(f"{count} valor(es) numérico(s) inválido(s) em {column}")

    key_frame = pd.DataFrame({"id": ids, "close_approach_date": dates.dt.date})
    duplicate_keys = int(key_frame.duplicated(keep=False).sum())
    if duplicate_keys:
        violations.append(f"{duplicate_keys} chave(s) duplicada(s) em (id, close_approach_date)")

    invalid_json_values = 0
    for value in dataframe["details_json"]:
        try:
            if isinstance(value, str):
                json.loads(value)
            elif not isinstance(value, (dict, list)):
                invalid_json_values += 1
        except (TypeError, json.JSONDecodeError):
            invalid_json_values += 1
    if invalid_json_values:
        violations.append(f"{invalid_json_values} payload(s) JSON inválido(s)")

    report = DataQualityReport(
        valid=not violations,
        rows_checked=rows_checked,
        duplicate_keys=duplicate_keys,
        null_ids=null_ids,
        invalid_dates=invalid_dates,
        invalid_numeric_values=invalid_numeric_values,
        invalid_json_values=invalid_json_values,
        violations=_as_violations(violations),
    )
    if not report.valid:
        LOGGER.warning("Data contract rejeitou lote: %s", "; ".join(report.violations))
    return report


def enforce_monitoring_contract(dataframe: pd.DataFrame) -> DataQualityReport:
    """Validate a batch and raise before any database write if invalid.

    Args:
        dataframe: Canonical dataframe about to be persisted.

    Returns:
        The successful validation report.

    Raises:
        DataContractError: If one or more blocking rules fail.
    """

    report = validate_monitoring_batch(dataframe)
    if not report.valid:
        raise DataContractError(report)
    return report
