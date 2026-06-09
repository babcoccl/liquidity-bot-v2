"""Impermanent loss calculations for Uniswap V3 concentrated liquidity positions.
All math uses Decimal — never float.
tick_lower and tick_upper define the active price range.
Price inputs are token1/token0 (i.e. token1Price from The Graph).
"""
# AUDIT:status=complete
# AUDIT:sprint=3

from __future__ import annotations

from decimal import Decimal


def tick_to_price(tick: int) -> Decimal:
    """Convert a tick to its corresponding price.

    Returns Decimal("1.0001") ** tick using Decimal arithmetic only.
    """
    base = Decimal("1.0001")
    if tick == 0:
        return Decimal("1")
    result = base ** abs(tick)
    if tick < 0:
        result = Decimal("1") / result
    return result


def liquidity_amounts(
    price: Decimal,
    price_lower: Decimal,
    price_upper: Decimal,
    capital_usd: Decimal,
) -> tuple[Decimal, Decimal]:
    """Compute token0 and token1 amounts for a position given current price and range boundaries.

    If price <= price_lower: position is 100% token0.
    If price >= price_upper: position is 100% token1.
    Otherwise: split position using V3 concentrated liquidity formula.

    Returns (amount0, amount1).
    """
    # Guard
    if price_lower <= Decimal("0") or price_upper <= price_lower or capital_usd <= Decimal("0"):
        return (Decimal("0"), Decimal("0"))

    if price <= Decimal("0"):
        return (Decimal("0"), Decimal("0"))

    if price <= price_lower:
        # 100% token0
        amount0 = capital_usd / price_lower
        amount1 = Decimal("0")
        return (amount0, amount1)

    if price >= price_upper:
        # 100% token1
        amount0 = Decimal("0")
        amount1 = capital_usd / price
        return (amount0, amount1)

    # In-range: split position using V3 formula
    sqrt_p = price.sqrt()
    sqrt_lower = price_lower.sqrt()
    sqrt_upper = price_upper.sqrt()

    # L = capital_usd / ((sqrt_p - sqrt_lower) + price * (1/sqrt_p - 1/sqrt_upper))
    term0 = sqrt_p - sqrt_lower
    term1 = price * (Decimal("1") / sqrt_p - Decimal("1") / sqrt_upper)
    L = capital_usd / (term0 + term1)

    amount0 = L * (Decimal("1") / sqrt_p - Decimal("1") / sqrt_upper)
    amount1 = L * (sqrt_p - sqrt_lower)

    return (amount0, amount1)


def position_value_usd(
    amount0: Decimal,
    amount1: Decimal,
    price: Decimal,
) -> Decimal:
    """Return current USD value of a liquidity position.

    Returns amount0 * price + amount1.
    Guard: if price <= 0 return 0.
    """
    if price <= Decimal("0"):
        return Decimal("0")
    return amount0 * price + amount1


def hodl_value_usd(
    amount0: Decimal,
    amount1: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
) -> Decimal:
    """Return value of holding initial tokens at current price.

    Returns amount0 * current_price + amount1.
    Guard: if entry_price <= 0 or current_price <= 0 return 0.
    """
    if entry_price <= Decimal("0") or current_price <= Decimal("0"):
        return Decimal("0")
    return amount0 * current_price + amount1


def compute_il(
    entry_price: Decimal,
    current_price: Decimal,
    price_lower: Decimal,
    price_upper: Decimal,
    capital_usd: Decimal,
) -> Decimal:
    """Full V3 IL computation.

    Compute LP value at current price vs HODL value.
    Negative result = loss relative to HODL.
    """
    if capital_usd <= Decimal("0"):
        return Decimal("0")

    # Step 1: compute entry amounts
    amount0, amount1 = liquidity_amounts(
        entry_price, price_lower, price_upper, capital_usd
    )

    # Step 2: recalculate amounts at current price as approximation
    current_amount0, current_amount1 = liquidity_amounts(
        current_price, price_lower, price_upper, capital_usd
    )

    # LP value at current price
    lp_val = position_value_usd(current_amount0, current_amount1, current_price)

    # HODL value
    hodl_val = hodl_value_usd(amount0, amount1, entry_price, current_price)

    if hodl_val <= Decimal("0"):
        return Decimal("0")

    il = lp_val - hodl_val
    return il


def compute_il_pct(
    entry_price: Decimal,
    current_price: Decimal,
    price_lower: Decimal,
    price_upper: Decimal,
    capital_usd: Decimal,
) -> Decimal:
    """Return IL as a percentage of capital.

    Returns compute_il(...) / capital_usd if capital_usd > 0 else 0.
    """
    if capital_usd <= Decimal("0"):
        return Decimal("0")
    il = compute_il(entry_price, current_price, price_lower, price_upper, capital_usd)
    return il / capital_usd


def il_vs_hodl_pnl(
    prices: list[Decimal],
    price_lower: Decimal,
    price_upper: Decimal,
    capital_usd: Decimal,
) -> dict:
    """Compare IL to HODL PnL over a price series.

    Takes a list of prices (ascending by date). Entry = prices[0], exit = prices[-1].

    Returns dict with il_usd, il_pct, hodl_pnl_usd, lp_pnl_usd, net_diff_usd.
    """
    if len(prices) < 2:
        return {
            "il_usd": Decimal("0"),
            "il_pct": Decimal("0"),
            "hodl_pnl_usd": Decimal("0"),
            "lp_pnl_usd": Decimal("0"),
            "net_diff_usd": Decimal("0"),
        }

    entry_price = prices[0]
    current_price = prices[-1]

    il_val = compute_il(entry_price, current_price, price_lower, price_upper, capital_usd)
    il_pct_val = compute_il_pct(
        entry_price, current_price, price_lower, price_upper, capital_usd
    )

    # HODL PnL: recompute amounts at entry, then value at current price minus capital
    amount0, amount1 = liquidity_amounts(
        entry_price, price_lower, price_upper, capital_usd
    )
    hodl_val = hodl_value_usd(amount0, amount1, entry_price, current_price)
    hodl_pnl = hodl_val - capital_usd

    # LP PnL: LP value at current price minus capital
    current_amount0, current_amount1 = liquidity_amounts(
        current_price, price_lower, price_upper, capital_usd
    )
    lp_val = position_value_usd(current_amount0, current_amount1, current_price)
    lp_pnl = lp_val - capital_usd

    net_diff = lp_pnl - hodl_pnl

    return {
        "il_usd": il_val,
        "il_pct": il_pct_val,
        "hodl_pnl_usd": hodl_pnl,
        "lp_pnl_usd": lp_pnl,
        "net_diff_usd": net_diff,
    }


def mark_to_market_usd(
    capital_usd: Decimal,
    entry_price_usd_volatile: Decimal,
    current_price_usd_volatile: Decimal,
    volatile_fraction: Decimal = Decimal("0.5"),
) -> Decimal:
    """COMPUTE MARK-TO-MARKET ADJUSTMENT FOR VOLATILE ASSET LEG.

    For a 50/50 LP position, half the capital is in a volatile
    token. As that token's USD price changes, the dollar value
    of the position changes proportionally on that half.

    This is SEPARATE from IL — IL measures the divergence loss
    vs holding. MTM measures the absolute USD value change of
    the volatile leg vs entry.

    Returns signed Decimal: positive = appreciation, negative = depreciation.
    Returns Decimal("0") if entry_price_usd_volatile is zero.

    Args:
        capital_usd:                  Entry capital in USD.
        entry_price_usd_volatile:     USD price of volatile token at entry.
        current_price_usd_volatile:   USD price of volatile token now.
        volatile_fraction:            Fraction of capital in volatile token.
                                      Default 0.5 (50/50 full-range position).
    """
    if entry_price_usd_volatile <= Decimal("0"):
        return Decimal("0")
    price_return = (
        current_price_usd_volatile / entry_price_usd_volatile
    ) - Decimal("1")
    return capital_usd * volatile_fraction * price_return
