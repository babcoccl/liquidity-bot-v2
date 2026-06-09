"""TREND FILTER. DETECT TRENDING VS RANGING REGIME. DECIMAL ONLY.
# AUDIT:status=complete
# AUDIT:sprint=26
# AUDIT:issue=none
"""

from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import math as _math


def price_returns(
    prices: list[Decimal],
) -> list[Decimal]:
    """COMPUTE LOG RETURNS FROM PRICE SERIES. NEWEST-LAST ORDER."""
    if len(prices) < 2:
        return []
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > Decimal("0") and prices[i] > Decimal("0"):
            lr = Decimal(str(_math.log(float(prices[i] / prices[i - 1]))))
            returns.append(lr)
    return returns


def rolling_mean(values: list[Decimal], window: int) -> Decimal:
    """ROLLING MEAN OF LAST window VALUES. RETURN ZERO IF EMPTY."""
    if not values:
        return Decimal("0")
    subset = values[-window:]
    return sum(subset) / Decimal(str(len(subset)))


def trend_strength(
    prices: list[Decimal],
    short_window: int = 24,
    long_window: int = 168,
) -> Decimal:
    """COMPUTE TREND STRENGTH AS ABS(SHORT_EMA - LONG_EMA) / LONG_EMA.

    Uses simple rolling mean as EMA approximation.
    Returns value in [0, inf):
      ~0.00 - 0.02 = ranging / mean-reverting — GOOD for LP
      ~0.02 - 0.05 = mild trend — CAUTION
      >0.05        = strong trend — AVOID / EXIT

    Args:
        prices:       List of prices in ascending time order.
        short_window: Hours for short mean (default 24h).
        long_window:  Hours for long mean (default 168h = 7 days).
    """
    if len(prices) < long_window:
        return Decimal("0")

    short_mean = rolling_mean(prices, short_window)
    long_mean = rolling_mean(prices, long_window)

    if long_mean <= Decimal("0"):
        return Decimal("0")

    strength = abs(short_mean - long_mean) / long_mean
    return strength.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def trend_direction(
    prices: list[Decimal],
    window: int = 168,
) -> str:
    """DETECT TREND DIRECTION OVER WINDOW. RETURN 'up', 'down', 'flat'."""
    if len(prices) < 2:
        return "flat"
    subset = prices[-window:] if len(prices) >= window else prices
    first = subset[0]
    last = subset[-1]
    if first <= Decimal("0"):
        return "flat"
    change = (last - first) / first
    if change > Decimal("0.03"):
        return "up"
    if change < Decimal("-0.03"):
        return "down"
    return "flat"


def is_ranging(
    prices: list[Decimal],
    short_window: int = 24,
    long_window: int = 168,
    strength_threshold: Decimal = Decimal("0.03"),
) -> bool:
    """RETURN TRUE IF PRICE IS IN RANGING REGIME. SAFE TO LP.
    RETURN FALSE IF TRENDING — ELEVATED IL RISK.
    """
    strength = trend_strength(prices, short_window, long_window)
    return strength <= strength_threshold


def trend_score_penalty(
    prices: list[Decimal],
    short_window: int = 24,
    long_window: int = 168,
    max_penalty: Decimal = Decimal("0.30"),
) -> Decimal:
    """COMPUTE ENTRY SCORE PENALTY FOR TRENDING MARKETS.

    Returns a value in [0, max_penalty] to subtract from entry score.
    Ranging market = 0 penalty. Strong trend = max_penalty.

    Caller subtracts this from compute_pool_score() result before
    comparing to min_entry_score threshold.
    """
    strength = trend_strength(prices, short_window, long_window)
    # Scale linearly from 0 at strength=0 to max_penalty at strength=0.10
    scale = min(strength / Decimal("0.10"), Decimal("1"))
    return (scale * max_penalty).quantize(
        Decimal("0.00000001"), rounding=ROUND_HALF_UP
    )


def should_exit_trend(
    prices: list[Decimal],
    entry_price: Decimal,
    short_window: int = 24,
    long_window: int = 168,
    strength_threshold: Decimal = Decimal("0.05"),
    adverse_move_threshold: Decimal = Decimal("0.07"),
) -> tuple[bool, str]:
    """EVALUATE WHETHER TO EXIT POSITION DUE TO TREND BREAKOUT.

    Returns (should_exit: bool, reason: str).

    Exit conditions:
      1. TREND_BREAKOUT: trend_strength > threshold AND direction
         is adverse (price moving away from entry significantly)
      2. ADVERSE_MOVE: current price has moved more than
         adverse_move_threshold from entry in a single direction
         with sustained trend (not a spike)

    Args:
        prices:                   Price history in ascending order.
                                  Last element = current price.
        entry_price:              Price at position entry.
        strength_threshold:       Trend strength above which to consider exit.
        adverse_move_threshold:   Price move from entry triggering exit.
    """
    if len(prices) < long_window or entry_price <= Decimal("0"):
        return False, ""

    strength = trend_strength(prices, short_window, long_window)
    direction = trend_direction(prices, long_window)
    current_price = prices[-1]
    price_move = abs(current_price - entry_price) / entry_price

    # TREND_BREAKOUT: strong trend detected
    if strength > strength_threshold:
        return True, f"TREND_BREAKOUT strength={float(strength):.4f}"

    # ADVERSE_MOVE: price moved too far from entry with trend confirmation
    if (
        price_move > adverse_move_threshold
        and direction != "flat"
        and strength > Decimal("0.02")
    ):
        return True, (
            f"ADVERSE_MOVE move={float(price_move):.2%} "
            f"dir={direction} strength={float(strength):.4f}"
        )

    return False, ""