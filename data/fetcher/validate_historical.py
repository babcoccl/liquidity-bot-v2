"""
Post-fetch validation for pool history records.
Supports both PoolDayData (daily) and PoolHistoryPoint (hourly) via duck-typing.
All checks return a list of ValidationError describing what failed on which record.
Never raises — always returns.
"""

# AUDIT:status=complete
# AUDIT:sprint=9

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, List


@dataclass(frozen=True)
class ValidationError:
    timestamp: int       # unix timestamp of the offending record
    field: str           # field name that failed
    message: str         # human-readable description


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _record_time(record: Any) -> int:
    """Return the time anchor for a record (hourly timestamp or daily date)."""
    if hasattr(record, "timestamp"):
        return record.timestamp
    return record.date


def _is_hourly(records: List[Any]) -> bool:
    """Detect if records are hourly-based (PoolHistoryPoint) vs daily (PoolDayData)."""
    if not records:
        return False
    return hasattr(records[0], "timestamp")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_no_gaps(
    records: List[Any],
    expected_interval_seconds: int | None = None,
) -> List[ValidationError]:
    """Check that consecutive records are no more than 2x the expected interval apart.

    For hourly records (detected via .timestamp), default interval is 3600s.
    For daily records (detected via .date), default interval is 86400s.
    Records must be sorted ascending by time before calling.
    """
    if not records:
        return []

    hourly = _is_hourly(records)
    if expected_interval_seconds is None:
        expected_interval_seconds = 3600 if hourly else 86400

    errors: List[ValidationError] = []
    for i in range(len(records) - 1):
        t_prev = _record_time(records[i])
        t_curr = _record_time(records[i + 1])
        diff = t_curr - t_prev
        if diff > expected_interval_seconds * 2:
            errors.append(ValidationError(
                timestamp=t_curr,
                field="timestamp" if hourly else "date",
                message=f"Gap of {diff} seconds between {t_prev} and {t_curr}",
            ))
    return errors


def validate_no_negative_values(
    records: List[Any],
) -> List[ValidationError]:
    """Check that volume_usd and tvl_usd are never negative."""
    errors: List[ValidationError] = []
    for record in records:
        t = _record_time(record)
        if record.volume_usd < 0:
            errors.append(ValidationError(
                timestamp=t,
                field="volume_usd",
                message=f"volume_usd is negative: {record.volume_usd} at {t}",
            ))
        if record.tvl_usd < 0:
            errors.append(ValidationError(
                timestamp=t,
                field="tvl_usd",
                message=f"tvl_usd is negative: {record.tvl_usd} at {t}",
            ))
    return errors


def validate_price_sanity(
    records: List[Any],
    max_change: Decimal = Decimal("0.5"),
) -> List[ValidationError]:
    """Check that price does not change by more than max_change between consecutive records."""
    errors: List[ValidationError] = []
    for i in range(len(records) - 1):
        prev_price = records[i].price_token1_in_token0
        if prev_price <= 0:
            continue
        curr_price = records[i + 1].price_token1_in_token0
        change = abs(curr_price - prev_price) / prev_price
        if change > max_change:
            t_prev = _record_time(records[i])
            t_curr = _record_time(records[i + 1])
            errors.append(ValidationError(
                timestamp=t_curr,
                field="price_token1_in_token0",
                message=f"Price changed by {change:.2%} between {t_prev} and {t_curr}",
            ))
    return errors


def validate_fee_growth_present(
    records: List[Any],
) -> List[ValidationError]:
    """Check that at least one fee_growth_global field is present on each record.

    Warning-only: GeckoTerminal sources always have None for these fields,
    so this will produce warnings for gecko_terminal-sourced data.
    """
    errors: List[ValidationError] = []
    for record in records:
        fg0 = getattr(record, "fee_growth_global_0", None)
        fg1 = getattr(record, "fee_growth_global_1", None)
        if fg0 is None and fg1 is None:
            t = _record_time(record)
            errors.append(ValidationError(
                timestamp=t,
                field="fee_growth_global",
                message=f"Both fee_growth_global fields are None at {t}",
            ))
    return errors


def validate_all(records: List[Any]) -> List[ValidationError]:
    """Run all validators in order and return combined list of errors."""
    combined: List[ValidationError] = []
    combined.extend(validate_no_gaps(records))
    combined.extend(validate_no_negative_values(records))
    combined.extend(validate_price_sanity(records))
    combined.extend(validate_fee_growth_present(records))
    return combined