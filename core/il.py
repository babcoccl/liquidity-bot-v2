"""Impermanent loss calculation utilities."""

from __future__ import annotations


def compute_impermanent_loss(
    prices: list[float],
    tick_lower: int | float,
    tick_upper: int | float,
) -> float:
    """Compute impermanent loss ratio for a price series within a tick range.

    Args:
        prices:     Ordered list of historical prices.
        tick_lower: Lower tick boundary (or price equivalent).
        tick_upper: Upper tick boundary (or price equivalent).

    Returns 0.0 when prices are unchanged (flat).
    Negative value = loss relative to HODL.
    """
    if len(prices) < 2:
        return 0.0
    price_0 = prices[0]
    price_1 = prices[-1]
    if price_0 <= 0 or price_1 <= 0:
        return 0.0
    ratio = price_1 / price_0
    if ratio == 1.0:
        return 0.0
    il = 2 * (ratio ** 0.5) / (1 + ratio) - 1
    # Return negative to indicate loss
    return -abs(il)


def compute_il_loss_dollar(capital_usd: float, current_value: float, entry_price: float) -> float:
    """Compute dollar IL loss for a position."""
    if capital_usd <= 0 or entry_price <= 0:
        return 0.0
    il_ratio = abs(compute_impermanent_loss([entry_price, max(current_value / capital_usd * entry_price, entry_price)], 0, 1))
    return capital_usd * il_ratio


def concentrated_liquidity_il(
    current_price: float,
    entry_price: float,
    tick_lower: float,
    tick_upper: float,
) -> float:
    """Return IL-adjusted ratio for a concentrated liquidity position.

    Returns 1.0 when price is unchanged. Value < 1 means IL loss.
    """
    if current_price <= 0 or entry_price <= 0:
        return 1.0
    ratio = current_price / entry_price
    if ratio == 1.0:
        return 1.0
    il_ratio = 2 * (ratio ** 0.5) / (1 + ratio)
    return max(0, il_ratio)


def compute_il_from_price_series(
    prices: list[float],
    tick_lower: int | float = 0,
    tick_upper: int | float = 1,
) -> float:
    """Compute cumulative IL across a price series."""
    return compute_impermanent_loss(prices, tick_lower, tick_upper)


def estimate_il_at_tick_range(
    prices: list[float],
    tick_lower_price: float,
    tick_upper_price: float,
) -> float:
    """Estimate IL for a concentrated position within [tick_lower, tick_upper]."""
    return compute_impermanent_loss(prices, tick_lower_price, tick_upper_price)


def il_vs_hodl_pnl(
    prices: list[float],
    deposit_value: float,
) -> dict:
    """Compare IL loss to HODL PnL.

    Returns dict with il_loss_usd, hodl_pnl_usd, and net_diff_usd.
    """
    if len(prices) < 2 or prices[0] <= 0:
        return {"il_loss_usd": 0.0, "hodl_pnl_usd": 0.0, "net_diff_usd": 0.0}

    price_0 = prices[0]
    price_1 = prices[-1]
    il_ratio = abs(compute_impermanent_loss(prices, 0, 1))
    hodl_ratio = (price_1 / price_0 - 1)

    return {
        "il_loss_usd": round(deposit_value * il_ratio, 4),
        "hodl_pnl_usd": round(deposit_value * hodl_ratio, 4),
        "net_diff_usd": round(deposit_value * (hodl_ratio + il_ratio), 4),
    }
