"""
Post-fetch validation for PoolDayData records.
All checks return a list of ValidationError describing what failed on which record.
Never raises — always returns.
"""

# AUDIT:status=complete
# AUDIT:sprint=5

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import List

from core.models import PoolDayData


@dataclass(frozen=True)
class ValidationError:
    date: int           # unix timestamp of the offending record
    field: str          # field name that failed
    message: str        # human-readable description


def validate_no_gaps(
    records: List[PoolDayData],
    expected_interval_seconds: int = 86400,
) -> List[ValidationError]:
    """Check that consecutive records are no more than 2x the expected interval apart.

    Records must be sorted ascending by date before calling (caller's responsibility).
    """
    errors: List[ValidationError] = []
    for i in range(len(records) - 1):
        diff = records[i + 1].date - records[i].date
        if diff > expected_interval_seconds * 2:
            errors.append(ValidationError(
                date=records[i + 1].date,
                field="date",
                message=f"Gap of {diff} seconds between {records[i].date} and {records[i + 1].date}",
            ))
    return errors


def validate_no_negative_values(
    records: List[PoolDayData],
) -> List[ValidationError]:
    """Check that volume_usd and tvl_usd are never negative."""
    errors: List[ValidationError] = []
    for record in records:
        if record.volume_usd < 0:
            errors.append(ValidationError(
                date=record.date,
                field="volume_usd",
                message=f"volume_usd is negative: {record.volume_usd} on date {record.date}",
            ))
        if record.tvl_usd < 0:
            errors.append(ValidationError(
                date=record.date,
                field="tvl_usd",
                message=f"tvl_usd is negative: {record.tvl_usd} on date {record.date}",
            ))
    return errors


def validate_price_sanity(
    records: List[PoolDayData],
    max_single_day_change: Decimal = Decimal("0.5"),
) -> List[ValidationError]:
    """Check that price does not change by more than max_single_day_change between consecutive days."""
    errors: List[ValidationError] = []
    for i in range(len(records) - 1):
        prev_price = records[i].price_token1_in_token0
        if prev_price <= 0:
            continue
        curr_price = records[i + 1].price_token1_in_token0
        change = abs(curr_price - prev_price) / prev_price
        if change > max_single_day_change:
            errors.append(ValidationError(
                date=records[i + 1].date,
                field="price_token1_in_token0",
                message=f"Price changed by {change:.2%} between {records[i].date} and {records[i + 1].date}",
            ))
    return errors


def validate_fee_growth_present(
    records: List[PoolDayData],
) -> List[ValidationError]:
    """Check that at least one fee_growth_global field is present on each record."""
    errors: List[ValidationError] = []
    for record in records:
        if record.fee_growth_global_0 is None and record.fee_growth_global_1 is None:
            errors.append(ValidationError(
                date=record.date,
                field="fee_growth_global",
                message=f"Both fee_growth_global fields are None on date {record.date}",
            ))
    return errors


def validate_all(records: List[PoolDayData]) -> List[ValidationError]:
    """Run all validators in order and return combined list of errors."""
    combined: List[ValidationError] = []
    combined.extend(validate_no_gaps(records))
    combined.extend(validate_no_negative_values(records))
    combined.extend(validate_price_sanity(records))
    combined.extend(validate_fee_growth_present(records))
    return combined