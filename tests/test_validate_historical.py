"""Tests for data.fetcher.validate_historical module."""

from decimal import Decimal

import pytest

from core.models import PoolDayData, PoolHistoryPoint
from data.fetcher.validate_historical import (
    validate_all,
    validate_fee_growth_present,
    validate_no_gaps,
    validate_no_negative_values,
    validate_price_sanity,
)


def _make_daily_record(
    date: int,
    volume: str = "1000.0",
    tvl: str = "50000.0",
    price: str = "2000.0",
    fee0=1000,
    fee1=2000,
) -> PoolDayData:
    p = Decimal(price)
    return PoolDayData(
        pool_address="0xabc",
        date=date,
        price_token1_in_token0=p,
        price_token0_in_token1=Decimal("1") / p if p > 0 else Decimal("0"),
        volume_usd=Decimal(volume),
        tvl_usd=Decimal(tvl),
        fee_growth_global_0=fee0,
        fee_growth_global_1=fee1,
        source="the_graph",
    )


def _make_hourly_record(
    timestamp: int,
    volume: str = "1000.0",
    tvl: str = "50000.0",
    price: str = "2000.0",
    fee0=None,
    fee1=None,
) -> PoolHistoryPoint:
    p = Decimal(price)
    return PoolHistoryPoint(
        pool_address="0xabc",
        timestamp=timestamp,
        price_token1_in_token0=p,
        price_token0_in_token1=Decimal("1") / p if p > 0 else Decimal("0"),
        volume_usd=Decimal(volume),
        tvl_usd=Decimal(tvl),
        fee_growth_global_0=fee0,
        fee_growth_global_1=fee1,
        source="gecko_terminal",
    )


# Alias for backward compat in existing tests
def _make_record(
    date: int,
    volume: str = "1000.0",
    tvl: str = "50000.0",
    price: str = "2000.0",
    fee0=1000,
    fee1=2000,
) -> PoolDayData:
    return _make_daily_record(date, volume, tvl, price, fee0, fee1)


# ---------------------------------------------------------------------------
# validate_no_gaps
# ---------------------------------------------------------------------------

class TestValidateNoGaps:
    def test_no_gaps_clean_daily_records(self) -> None:
        records = [
            _make_record(1000000000),
            _make_record(1000086400),
            _make_record(1000172800),
        ]
        assert validate_no_gaps(records) == []

    def test_no_gaps_detects_missing_day(self) -> None:
        records = [
            _make_daily_record(1000000000),
            _make_daily_record(1000259200),  # 3 days later (> 86400 * 2)
        ]
        errors = validate_no_gaps(records)
        assert len(errors) == 1
        assert errors[0].field == "date"
        assert "Gap of" in errors[0].message

    # ------------------------------------------------------------------
    # Hourly record tests
    # ------------------------------------------------------------------

    def test_hourly_no_gaps_clean_3600_spacing(self) -> None:
        """Hourly records with 3600s spacing pass validation."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000003600),
            _make_hourly_record(1000007200),
            _make_hourly_record(1000010800),
        ]
        assert validate_no_gaps(records) == []

    def test_hourly_gap_3_hours_fails(self) -> None:
        """A 3-hour gap (10800s > 3600*2=7200) is flagged."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000010800),  # 3 hours later
        ]
        errors = validate_no_gaps(records)
        assert len(errors) == 1
        assert errors[0].field == "timestamp"
        assert "Gap of 10800" in errors[0].message

    def test_hourly_gap_exactly_2_hours_passes(self) -> None:
        """A 2-hour gap (7200s == 3600*2) is at the boundary and passes."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000007200),
        ]
        assert validate_no_gaps(records) == []

    def test_hourly_duplicate_timestamps_handled(self) -> None:
        """Duplicate timestamps produce zero-diff which passes."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000000000),
            _make_hourly_record(1000003600),
        ]
        assert validate_no_gaps(records) == []

    def test_mixed_interval_explicit_override(self) -> None:
        """Caller can override expected interval explicitly."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000010800),  # 3h gap
        ]
        # With default hourly (3600), this fails. With explicit 7200, it passes.
        assert len(validate_no_gaps(records)) == 1
        assert validate_no_gaps(records, expected_interval_seconds=7200) == []

    def test_no_gaps_empty_list_returns_empty(self) -> None:
        assert validate_no_gaps([]) == []

    def test_no_gaps_single_record_returns_empty(self) -> None:
        assert validate_no_gaps([_make_record(1000000000)]) == []


# ---------------------------------------------------------------------------
# validate_no_negative_values
# ---------------------------------------------------------------------------

class TestValidateNoNegativeValues:
    def test_no_negative_clean_records(self) -> None:
        records = [
            _make_record(1000000000),
            _make_record(1000086400),
        ]
        assert validate_no_negative_values(records) == []

    def test_no_negative_detects_negative_volume(self) -> None:
        records = [_make_record(1000000000, volume="-100.0")]
        errors = validate_no_negative_values(records)
        assert len(errors) == 1
        assert errors[0].field == "volume_usd"

    def test_no_negative_detects_negative_tvl(self) -> None:
        records = [_make_record(1000000000, tvl="-500.0")]
        errors = validate_no_negative_values(records)
        assert len(errors) == 1
        assert errors[0].field == "tvl_usd"

    def test_no_negative_empty_list_returns_empty(self) -> None:
        assert validate_no_negative_values([]) == []


# ---------------------------------------------------------------------------
# validate_price_sanity
# ---------------------------------------------------------------------------

class TestValidatePriceSanity:
    def test_price_sanity_clean_records(self) -> None:
        records = [
            _make_record(1000000000, price="2000.0"),
            _make_record(1000086400, price="2100.0"),
        ]
        assert validate_price_sanity(records) == []

    def test_price_sanity_detects_large_move(self) -> None:
        records = [
            _make_record(1000000000, price="2000.0"),
            _make_record(1000086400, price="4000.0"),  # 100% change
        ]
        errors = validate_price_sanity(records)
        assert len(errors) == 1
        assert errors[0].field == "price_token1_in_token0"

    def test_price_sanity_ignores_zero_price(self) -> None:
        records = [
            _make_record(1000000000, price="0"),
            _make_record(1000086400, price="2000.0"),
        ]
        assert validate_price_sanity(records) == []

    def test_price_sanity_empty_list_returns_empty(self) -> None:
        assert validate_price_sanity([]) == []


# ---------------------------------------------------------------------------
# validate_fee_growth_present
# ---------------------------------------------------------------------------

class TestValidateFeeGrowthPresent:
    def test_fee_growth_clean_records_both_present(self) -> None:
        records = [
            _make_record(1000000000, fee0=1000, fee1=2000),
            _make_record(1000086400, fee0=3000, fee1=4000),
        ]
        assert validate_fee_growth_present(records) == []

    def test_fee_growth_clean_one_field_none_is_ok(self) -> None:
        records = [
            _make_record(1000000000, fee0=None, fee1=2000),
            _make_record(1000086400, fee0=3000, fee1=None),
        ]
        assert validate_fee_growth_present(records) == []

    def test_fee_growth_detects_both_none(self) -> None:
        records = [_make_record(1000000000, fee0=None, fee1=None)]
        errors = validate_fee_growth_present(records)
        assert len(errors) == 1
        assert errors[0].field == "fee_growth_global"

    def test_fee_growth_empty_list_returns_empty(self) -> None:
        assert validate_fee_growth_present([]) == []


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

class TestValidateAll:
    def test_validate_all_clean_returns_empty(self) -> None:
        records = [
            _make_daily_record(1000000000),
            _make_daily_record(1000086400),
        ]
        assert validate_all(records) == []

    def test_validate_all_collects_errors_from_all_validators(self) -> None:
        records = [
            _make_daily_record(1000000000, volume="-1.0", price="2000.0", fee0=None, fee1=None),
            _make_daily_record(1000259200, tvl="-1.0", price="8000.0", fee0=None, fee1=None),
        ]
        errors = validate_all(records)
        # Should collect: gap, negative volume, negative tvl, price change, 2x fee_growth
        assert len(errors) >= 4

    def test_validate_all_hourly_clean(self) -> None:
        """Hourly records with clean data pass all validators (except fee_growth warning)."""
        records = [
            _make_hourly_record(1000000000, price="2000.0"),
            _make_hourly_record(1000003600, price="2050.0"),
        ]
        errors = validate_all(records)
        # fee_growth warnings expected (both None for gecko_terminal)
        assert any(e.field == "fee_growth_global" for e in errors)
        # No gap errors
        assert not any(e.field == "timestamp" and "Gap" in e.message for e in errors)

    def test_validate_all_hourly_with_gaps(self) -> None:
        """Hourly records with a 4-hour gap are flagged."""
        records = [
            _make_hourly_record(1000000000),
            _make_hourly_record(1000014400),  # 4h gap > 7200 threshold
        ]
        errors = validate_all(records)
        assert any(e.field == "timestamp" and "Gap of 14400" in e.message for e in errors)
