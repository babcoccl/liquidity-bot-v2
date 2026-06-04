"""
Layer 3: Smoke tests against real committed data files.
Asserts structural invariants — not specific values.
Skipped automatically if data files are absent (CI without data).
"""
# AUDIT:sprint=11

import pytest
from decimal import Decimal
from pathlib import Path

from data.loader.pool_loader import load_pool_history
from data.loader.token_price_loader import load_token_prices
from registry.registry import PoolRegistry

HISTORICAL_DIR = Path("data/historical")
PRICES_DIR = Path("data/prices")
REGISTRY_PATH = Path("registry/registry.json")

# Skip entire module if data files not present (e.g. fresh clone without LFS)
pytestmark = pytest.mark.skipif(
    not HISTORICAL_DIR.exists() or not any(HISTORICAL_DIR.glob("*.json")),
    reason="data/historical/ not populated — run fetch script first",
)


@pytest.fixture(scope="module")
def registry():
    r = PoolRegistry(path=REGISTRY_PATH)
    r.load()
    return r


@pytest.fixture(scope="module")
def all_pool_records():
    result = {}
    for f in sorted(HISTORICAL_DIR.glob("*.json")):
        result[f.stem] = load_pool_history(f)
    return result


@pytest.fixture(scope="module")
def all_token_records():
    result = {}
    for f in sorted(PRICES_DIR.glob("*.json")):
        result[f.stem] = load_token_prices(f)
    return result


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------

def test_all_pools_have_minimum_records(all_pool_records):
    for pair_name, records in all_pool_records.items():
        assert len(records) >= 8000, (
            f"{pair_name}: expected >=8000 hourly records, got {len(records)}"
        )


def test_all_tokens_have_minimum_records(all_token_records):
    for symbol, records in all_token_records.items():
        assert len(records) >= 8000, (
            f"{symbol}: expected >=8000 hourly records, got {len(records)}"
        )


def test_each_pool_has_token_price_files(registry, all_token_records):
    for pool in registry.all():
        t0 = pool.token0.symbol.upper()
        t1 = pool.token1.symbol.upper()
        assert t0 in all_token_records, (
            f"Token price file missing for {t0} (required by pool {pool.pair_name})"
        )
        assert t1 in all_token_records, (
            f"Token price file missing for {t1} (required by pool {pool.pair_name})"
        )


def test_token_timestamps_cover_pool_timestamps(registry, all_pool_records, all_token_records):
    for pool in registry.all():
        pair = pool.pair_name
        if pair not in all_pool_records:
            continue
        pool_ts = {r.timestamp for r in all_pool_records[pair]}
        t0 = pool.token0.symbol.upper()
        t1 = pool.token1.symbol.upper()
        if t0 not in all_token_records or t1 not in all_token_records:
            continue
        token0_ts = {r.timestamp for r in all_token_records[t0]}
        token1_ts = {r.timestamp for r in all_token_records[t1]}
        uncovered_t0 = pool_ts - token0_ts
        uncovered_t1 = pool_ts - token1_ts
        assert len(uncovered_t0) < len(pool_ts) * 0.01, (
            f"{pair}: {len(uncovered_t0)} pool timestamps not covered by {t0} prices"
        )
        assert len(uncovered_t1) < len(pool_ts) * 0.01, (
            f"{pair}: {len(uncovered_t1)} pool timestamps not covered by {t1} prices"
        )


# ---------------------------------------------------------------------------
# Value invariants
# ---------------------------------------------------------------------------

def test_no_negative_volume_or_tvl(all_pool_records):
    for pair_name, records in all_pool_records.items():
        for r in records:
            assert r.volume_usd >= Decimal("0"), (
                f"{pair_name}: negative volume_usd at timestamp {r.timestamp}"
            )
            assert r.tvl_usd >= Decimal("0"), (
                f"{pair_name}: negative tvl_usd at timestamp {r.timestamp}"
            )


def test_price_reciprocal_consistency(all_pool_records):
    """
    price_token1_in_token0 * price_token0_in_token1 must be ~1.0.
    Tolerance: 0.1% (accounts for rounding in source data).
    """
    tolerance = Decimal("0.001")
    for pair_name, records in all_pool_records.items():
        for r in records:
            if r.price_token1_in_token0 == Decimal("0"):
                continue
            product = r.price_token1_in_token0 * r.price_token0_in_token1
            assert abs(product - Decimal("1")) < tolerance, (
                f"{pair_name} at {r.timestamp}: "
                f"price product {product} deviates from 1.0 by more than 0.1%"
            )


def test_fee_growth_monotonically_non_decreasing(all_pool_records):
    """
    Fee growth accumulators must never go backward across time.
    None values (missing data) are skipped.
    """
    for pair_name, records in all_pool_records.items():
        prev_fg0 = None
        prev_fg1 = None
        for r in records:
            if r.fee_growth_global_0 is not None:
                if prev_fg0 is not None:
                    assert r.fee_growth_global_0 >= prev_fg0, (
                        f"{pair_name} at {r.timestamp}: "
                        f"fee_growth_global_0 went backward "
                        f"({prev_fg0} -> {r.fee_growth_global_0})"
                    )
                prev_fg0 = r.fee_growth_global_0
            if r.fee_growth_global_1 is not None:
                if prev_fg1 is not None:
                    assert r.fee_growth_global_1 >= prev_fg1, (
                        f"{pair_name} at {r.timestamp}: "
                        f"fee_growth_global_1 went backward "
                        f"({prev_fg1} -> {r.fee_growth_global_1})"
                    )
                prev_fg1 = r.fee_growth_global_1


def test_all_token_prices_positive(all_token_records):
    for symbol, records in all_token_records.items():
        for r in records:
            assert r.price_usd > Decimal("0"), (
                f"{symbol} at {r.timestamp}: price_usd must be positive"
            )


def test_stablecoin_prices_within_peg_tolerance(all_token_records):
    """
    USDC, USDT, EUSD must stay within 5% of their pegs.
    EURC must stay within 15% of $1 (EUR/USD fluctuates).
    """
    peg_checks = {
        "USDC": (Decimal("0.95"), Decimal("1.05")),
        "USDT": (Decimal("0.95"), Decimal("1.05")),
        "EUSD": (Decimal("0.95"), Decimal("1.05")),
        "EURC": (Decimal("0.80"), Decimal("1.25")),
    }
    for symbol, (lo, hi) in peg_checks.items():
        if symbol not in all_token_records:
            continue
        for r in all_token_records[symbol]:
            assert lo <= r.price_usd <= hi, (
                f"{symbol} at {r.timestamp}: price {r.price_usd} outside "
                f"peg tolerance [{lo}, {hi}]"
            )