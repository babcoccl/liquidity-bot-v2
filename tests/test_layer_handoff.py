"""
Layer 2: Integration tests — loader -> calculator handoff.
Loads fixture files, passes through calculation path, asserts correctness.
"""
# AUDIT:sprint=11

import pytest
from decimal import Decimal
from pathlib import Path

from data.loader.pool_loader import load_pool_history
from data.loader.token_price_loader import load_token_prices
from strategy.il_calculator import il_from_token_prices, il_between_timestamps

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def pool_records():
    return load_pool_history(FIXTURES / "pool_WETH-USDC_sample.json")


@pytest.fixture
def weth_prices():
    return load_token_prices(FIXTURES / "prices_WETH_sample.json")


@pytest.fixture
def usdc_prices():
    return load_token_prices(FIXTURES / "prices_USDC_sample.json")


# ---------------------------------------------------------------------------
# Schema and type integrity
# ---------------------------------------------------------------------------

def test_pool_records_load_as_correct_type(pool_records):
    from core.models import PoolHistoryPoint
    assert all(isinstance(r, PoolHistoryPoint) for r in pool_records)


def test_pool_records_price_fields_are_decimal(pool_records):
    for r in pool_records:
        assert isinstance(r.price_token1_in_token0, Decimal), (
            f"price_token1_in_token0 must be Decimal, got {type(r.price_token1_in_token0)}"
        )
        assert isinstance(r.price_token0_in_token1, Decimal)
        assert isinstance(r.volume_usd, Decimal)
        assert isinstance(r.tvl_usd, Decimal)


def test_token_prices_load_as_correct_type(weth_prices):
    from core.models import TokenHistoryPoint
    assert all(isinstance(r, TokenHistoryPoint) for r in weth_prices)


def test_token_price_usd_is_decimal(weth_prices):
    for r in weth_prices:
        assert isinstance(r.price_usd, Decimal), (
            f"price_usd must be Decimal, got {type(r.price_usd)}"
        )


def test_pool_address_injected_from_wrapper(pool_records):
    for r in pool_records:
        assert r.pool_address == "0xb4cb800910b228ed3d0834cf79d697127bbb00e5"


def test_token_symbol_injected_from_wrapper(weth_prices):
    for r in weth_prices:
        assert r.symbol == "WETH"


# ---------------------------------------------------------------------------
# Timestamp alignment
# ---------------------------------------------------------------------------

def test_fixture_timestamps_align(pool_records, weth_prices, usdc_prices):
    pool_ts = {r.timestamp for r in pool_records}
    weth_ts = {r.timestamp for r in weth_prices}
    usdc_ts = {r.timestamp for r in usdc_prices}
    assert pool_ts == weth_ts == usdc_ts, (
        "All fixture files must share identical timestamps"
    )


def test_records_sorted_ascending(pool_records, weth_prices):
    pool_ts = [r.timestamp for r in pool_records]
    weth_ts = [r.timestamp for r in weth_prices]
    assert pool_ts == sorted(pool_ts)
    assert weth_ts == sorted(weth_ts)


# ---------------------------------------------------------------------------
# IL calculation through full handoff
# ---------------------------------------------------------------------------

def test_il_entry_to_exit_2x_move(pool_records, weth_prices, usdc_prices):
    """Entry: record 0 (WETH=$2000), Exit: record 4 (WETH=$4000). Expected IL ~ -5.719%."""
    il = il_from_token_prices(
        token0_price_entry=weth_prices[0].price_usd,
        token0_price_exit=weth_prices[4].price_usd,
        token1_price_entry=usdc_prices[0].price_usd,
        token1_price_exit=usdc_prices[4].price_usd,
    )
    assert abs(il - Decimal("-0.05719")) < Decimal("0.0001"), (
        f"Expected IL ~-5.719%, got {il}"
    )


def test_il_matches_between_pool_method_and_token_price_method(
    pool_records, weth_prices, usdc_prices
):
    """
    il_between_timestamps (uses pool's internal price) and
    il_from_token_prices (uses external token USD prices) must agree
    within tolerance when USDC is stable at $1.00.

    Test with record 0 -> record 4 (2x move).
    """
    il_pool = il_between_timestamps(pool_records[0], pool_records[4])
    il_tokens = il_from_token_prices(
        token0_price_entry=weth_prices[0].price_usd,
        token0_price_exit=weth_prices[4].price_usd,
        token1_price_entry=usdc_prices[0].price_usd,
        token1_price_exit=usdc_prices[4].price_usd,
    )
    assert abs(il_pool - il_tokens) < Decimal("0.0001"), (
        f"Pool-based IL {il_pool} and token-price-based IL {il_tokens} "
        f"must agree within 0.01%"
    )


def test_il_intermediate_move(pool_records, weth_prices, usdc_prices):
    """Entry: record 0 ($2000), Exit: record 2 ($2400) — k=1.2. IL ~ -0.414%."""
    il = il_from_token_prices(
        token0_price_entry=weth_prices[0].price_usd,
        token0_price_exit=weth_prices[2].price_usd,
        token1_price_entry=usdc_prices[0].price_usd,
        token1_price_exit=usdc_prices[2].price_usd,
    )
    assert abs(il - Decimal("-0.00414")) < Decimal("0.0001")


def test_il_output_is_decimal_not_float(pool_records, weth_prices, usdc_prices):
    il = il_from_token_prices(
        weth_prices[0].price_usd, weth_prices[4].price_usd,
        usdc_prices[0].price_usd, usdc_prices[4].price_usd,
    )
    assert isinstance(il, Decimal), "IL output must be Decimal"


def test_missing_price_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_token_prices(FIXTURES / "prices_NONEXISTENT.json")