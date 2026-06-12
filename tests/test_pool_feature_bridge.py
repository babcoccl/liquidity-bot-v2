"""
test_pool_feature_bridge.py — Unit tests for data.features.pool_feature_bridge.

Covers build_pool_metrics() and build_all_pool_metrics() across all
code paths: valid inputs, token resolution fallbacks, empty data,
error handling, and output type/structure contracts.

# AUDIT:status=complete
# AUDIT:sprint=36
"""

from decimal import Decimal

import pandas as pd
import pytest

from core.models import PoolHistoryPoint
from data.features.pool_feature_bridge import build_pool_metrics, build_all_pool_metrics
from registry.types import PoolConfig, TokenConfig


# ── PoolConfig factory ───────────────────────────────────────────────────────

def _make_pool_cfg(
    pool_address: str = "0xabc",
    pair_name: str = "WETH-USDC",
    token0_symbol: str = "WETH",
    token1_symbol: str = "USDC",
    fee_tier: int = 500,
    tick_lower: int = -887272,
    tick_upper: int = 887272,
) -> PoolConfig:
    return PoolConfig(
        pool_address=pool_address,
        pair_name=pair_name,
        token0=TokenConfig(symbol=token0_symbol, address="0x111", decimals=18),
        token1=TokenConfig(symbol=token1_symbol, address="0x222", decimals=6),
        fee_tier=fee_tier,
        price_reference={},
        tick_lower=tick_lower,
        tick_upper=tick_upper,
    )


# ── PoolHistoryPoint factory ─────────────────────────────────────────────────

def _make_pool_records(
    n: int = 100,
    base_ts: int = 1_700_000_000,
    price: str = "2000.00",
    volume: str = "500000.00",
    tvl: str = "5000000.00",
    pool_address: str = "0xabc",
) -> list[PoolHistoryPoint]:
    return [
        PoolHistoryPoint(
            pool_address=pool_address,
            timestamp=base_ts + i * 3600,
            price_token1_in_token0=Decimal(price),
            price_token0_in_token1=Decimal("1") / Decimal(price),
            volume_usd=Decimal(volume),
            tvl_usd=Decimal(tvl),
            fee_growth_global_0=None,
            fee_growth_global_1=None,
            source="gecko_terminal",
        )
        for i in range(n)
    ]


# ── Price DataFrame factory ──────────────────────────────────────────────────

def _make_price_df(
    symbol: str = "WETH",
    n: int = 200,
    base_price: float = 2000.0,
    price_step: float = 1.0,
    base_ts: int = 1_700_000_000,
) -> pd.DataFrame:
    timestamps = [base_ts + i * 3600 for i in range(n)]
    prices = [base_price + i * price_step for i in range(n)]
    idx = pd.to_datetime(timestamps, unit="s", utc=True)
    idx.name = "datetime"
    return pd.DataFrame(
        {
            "symbol": symbol,
            "price_usd": prices,
            "volume_usd": [1_000_000.0] * n,
            "market_cap_usd": [0.0] * n,
            "source": "coingecko",
        },
        index=idx,
    ).astype({"price_usd": "float64", "volume_usd": "float64"})


# ═══════════════════════════════════════════════════════════════════════════════
# build_pool_metrics tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_pool_metrics_returns_dict():
    """Test 1: Valid inputs return a dict."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, _make_pool_records())
    assert isinstance(result, dict)


def test_output_keys_complete():
    """Test 2: Output contains all expected keys."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, _make_pool_records())
    expected_keys = {
        "pool_id", "pair_name",
        "net_lp_alpha_30d", "annualized_vol_30d", "fee_apr", "volume_tvl_ratio",
        "vol_24h", "momentum_24h", "momentum_168h", "vol_momentum_24h",
        "price_features_ok", "pool_records_ok",
    }
    assert set(result.keys()) == expected_keys


def test_pool_id_is_lowercase():
    """Test 3: pool_id is lowercase regardless of input case."""
    cfg = _make_pool_cfg(pool_address="0xABC")
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, _make_pool_records())
    assert result["pool_id"] == "0xabc"


def test_financial_metric_values_are_decimal():
    """Test 4: All financial metric values are Decimal instances."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, _make_pool_records())
    decimal_keys = [
        "net_lp_alpha_30d", "annualized_vol_30d", "fee_apr", "volume_tvl_ratio",
        "vol_24h", "momentum_24h", "momentum_168h", "vol_momentum_24h",
    ]
    for key in decimal_keys:
        assert isinstance(result[key], Decimal), f"{key} is {type(result[key])}, expected Decimal"


def test_price_features_ok_true_when_token0_found():
    """Test 5: price_features_ok=True when token0 symbol is in price_dfs."""
    cfg = _make_pool_cfg(token0_symbol="WETH", token1_symbol="USDC")
    price_dfs = {"WETH": _make_price_df(symbol="WETH")}
    result = build_pool_metrics(cfg, price_dfs, _make_pool_records())
    assert result["price_features_ok"] is True


def test_price_features_ok_falls_back_to_token1():
    """Test 6: Falls back to token1 when token0 not in price_dfs."""
    cfg = _make_pool_cfg(token0_symbol="WETH", token1_symbol="USDC")
    price_dfs = {"USDC": _make_price_df(symbol="USDC")}  # only token1 present
    result = build_pool_metrics(cfg, price_dfs, _make_pool_records())
    assert result["price_features_ok"] is True


def test_price_features_ok_false_when_no_token_found():
    """Test 7: price_features_ok=False and zero features when no token data."""
    cfg = _make_pool_cfg(token0_symbol="WETH", token1_symbol="USDC")
    result = build_pool_metrics(cfg, {}, _make_pool_records())
    assert result["price_features_ok"] is False
    assert result["vol_24h"] == Decimal("0")
    assert result["momentum_24h"] == Decimal("0")


def test_pool_records_ok_true_when_records_present():
    """Test 8: pool_records_ok=True with non-empty records."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, _make_pool_records(n=100))
    assert result["pool_records_ok"] is True


def test_pool_records_ok_false_when_empty():
    """Test 9: pool_records_ok=False with empty records list."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, [])
    assert result["pool_records_ok"] is False


def test_vol_24h_is_nonzero_with_valid_price_data():
    """Test 10: vol_24h > 0 with sufficient price data."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df(n=200, price_step=1.0)}, _make_pool_records())
    assert result["vol_24h"] > Decimal("0")


def test_momentum_24h_is_nonzero_with_price_trend():
    """Test 11: momentum_24h != 0 with clear price trend."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df(n=200, price_step=10.0)}, _make_pool_records())
    assert result["momentum_24h"] != Decimal("0")


def test_empty_pool_records_returns_zero_metrics():
    """Test 12: Empty pool records produce zero entry metrics."""
    cfg = _make_pool_cfg()
    result = build_pool_metrics(cfg, {"WETH": _make_price_df()}, [])
    assert result["net_lp_alpha_30d"] == Decimal("0")
    assert result["fee_apr"] == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# build_all_pool_metrics tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_build_all_pool_metrics_returns_list():
    """Test 13: Returns a list with one entry per pool config."""
    cfg1 = _make_pool_cfg(pool_address="0xaaa", pair_name="WETH-USDC")
    cfg2 = _make_pool_cfg(
        pool_address="0xbbb", pair_name="WETH-cbBTC",
        token0_symbol="WETH", token1_symbol="cbBTC"
    )
    price_dfs = {"WETH": _make_price_df(symbol="WETH")}
    records_map = {"0xaaa": _make_pool_records(pool_address="0xaaa")}
    result = build_all_pool_metrics([cfg1, cfg2], price_dfs, records_map)
    assert isinstance(result, list)
    assert len(result) == 2


def test_build_all_pool_metrics_missing_records_uses_empty():
    """Test 14: Pools missing from pool_records_map get empty records (no exception)."""
    cfg = _make_pool_cfg(pool_address="0xzzz")
    result = build_all_pool_metrics([cfg], {}, {})
    assert len(result) == 1
    assert result[0]["pool_records_ok"] is False