"""TESTS FOR strategy/trend.py — TREND FILTER MODULE. DECIMAL ONLY."""
# AUDIT:status=complete
# AUDIT:sprint=26

from __future__ import annotations

import pytest
from decimal import Decimal

from strategy.trend import (
    price_returns,
    rolling_mean,
    trend_strength,
    trend_direction,
    is_ranging,
    trend_score_penalty,
    should_exit_trend,
)


# ─── price_returns ──────────────────────────────────────────────

def test_price_returns_empty() -> None:
    assert price_returns([]) == []

def test_price_returns_single() -> None:
    assert price_returns([Decimal("100")]) == []

def test_price_returns_flat() -> None:
    prices = [Decimal("100")] * 5
    result = price_returns(prices)
    assert len(result) == 4
    for r in result:
        assert abs(r) < Decimal("0.0000001")

def test_price_returns_rising() -> None:
    prices = [Decimal(str(i)) for i in range(1, 6)]
    result = price_returns(prices)
    assert len(result) == 4
    for r in result:
        assert r > Decimal("0")


# ─── rolling_mean ──────────────────────────────────────────────

def test_rolling_mean_empty() -> None:
    assert rolling_mean([], 5) == Decimal("0")

def test_rolling_mean_basic() -> None:
    vals = [Decimal(str(i)) for i in range(1, 6)]  # 1,2,3,4,5
    m = rolling_mean(vals, 5)
    assert abs(m - Decimal("3")) < Decimal("0.001")

def test_rolling_mean_window_smaller() -> None:
    vals = [Decimal(str(i)) for i in range(1, 6)]  # 1,2,3,4,5
    m = rolling_mean(vals, 3)
    assert abs(m - Decimal("4")) < Decimal("0.001")


# ─── trend_strength ──────────────────────────────────────────────

def test_trend_strength_flat() -> None:
    prices = [Decimal("100")] * 200
    s = trend_strength(prices)
    assert abs(s) < Decimal("0.01")

def test_trend_strength_rising() -> None:
    # Strong upward trend: 100 → 150 over 200 hours
    prices = [Decimal(str(100 + i)) for i in range(200)]
    s = trend_strength(prices)
    assert s > Decimal("0.05")

def test_trend_strength_too_short() -> None:
    prices = [Decimal("100"), Decimal("200")]
    s = trend_strength(prices)
    assert s == Decimal("0")


# ─── trend_direction ──────────────────────────────────────────────

def test_trend_direction_up() -> None:
    prices = [Decimal(str(100 + i)) for i in range(200)]
    d = trend_direction(prices)
    assert d == "up"

def test_trend_direction_down() -> None:
    prices = [Decimal(str(300 - i)) for i in range(200)]
    d = trend_direction(prices)
    assert d == "down"

def test_trend_direction_flat() -> None:
    prices = [Decimal("100")] * 200
    d = trend_direction(prices)
    assert d == "flat"

def test_trend_direction_single() -> None:
    d = trend_direction([Decimal("100")])
    assert d == "flat"


# ─── is_ranging ──────────────────────────────────────────────

def test_is_ranging_flat() -> None:
    prices = [Decimal("100")] * 200
    assert is_ranging(prices) is True

def test_is_ranging_trending() -> None:
    prices = [Decimal(str(100 + i)) for i in range(200)]
    assert is_ranging(prices) is False


# ─── trend_score_penalty ──────────────────────────────────────

def test_trend_score_penalty_flat() -> None:
    prices = [Decimal("100")] * 200
    pen = trend_score_penalty(prices)
    assert abs(pen) < Decimal("0.01")

def test_trend_score_penalty_trending() -> None:
    prices = [Decimal(str(100 + i)) for i in range(200)]
    pen = trend_score_penalty(prices)
    assert pen > Decimal("0")


# ─── should_exit_trend ──────────────────────────────────────

def test_should_exit_trend_flat() -> None:
    prices = [Decimal("100")] * 200
    exit_flag, reason = should_exit_trend(prices, entry_price=Decimal("100"))
    assert exit_flag is False
    assert reason == ""

def test_should_exit_trend_strong_rise() -> None:
    # Strong upward trend from entry
    prices = [Decimal(str(100 + i)) for i in range(200)]
    exit_flag, reason = should_exit_trend(prices, entry_price=Decimal("100"))
    assert exit_flag is True
    assert "TREND_BREAKOUT" in reason or "ADVERSE_MOVE" in reason

def test_should_exit_trend_too_short() -> None:
    prices = [Decimal("100"), Decimal("200")]
    exit_flag, reason = should_exit_trend(prices, entry_price=Decimal("100"))
    assert exit_flag is False


# ─── edge cases ──────────────────────────────────────────────

def test_should_exit_zero_entry() -> None:
    prices = [Decimal(str(i)) for i in range(200)]
    exit_flag, _ = should_exit_trend(prices, entry_price=Decimal("0"))
    assert exit_flag is False

def test_rolling_mean_no_values() -> None:
    m = rolling_mean([], 10)
    assert m == Decimal("0")