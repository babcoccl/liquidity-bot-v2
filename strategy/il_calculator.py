"""
ILCalculator — pure functions for impermanent loss and price ratio math.

All values are Decimal. Never cast to float internally.
IL is returned as a negative Decimal (loss) or zero (no divergence).
"""
# AUDIT:status=complete
# AUDIT:sprint=11

from decimal import Decimal, getcontext

getcontext().prec = 28

ZERO = Decimal("0")
ONE = Decimal("1")
TWO = Decimal("2")


def price_ratio(
    price_exit: Decimal,
    price_entry: Decimal,
) -> Decimal:
    """
    Compute k = price_exit / price_entry.

    Both prices must be expressed as token1_per_token0 (same direction).
    Raises ValueError if price_entry is zero.
    """
    if price_entry == ZERO:
        raise ValueError("price_entry must be non-zero")
    return price_exit / price_entry


def impermanent_loss(k: Decimal) -> Decimal:
    """
    Compute impermanent loss given price ratio k = P_exit / P_entry.

    Formula: IL = (2 * sqrt(k) / (1 + k)) - 1

    Returns a Decimal <= 0. Zero means no divergence.
    Raises ValueError if k <= 0.
    """
    if k <= ZERO:
        raise ValueError(f"price ratio k must be positive, got {k}")
    sqrt_k = k.sqrt()
    return (TWO * sqrt_k / (ONE + k)) - ONE


def il_between_timestamps(
    pool_record_entry,
    pool_record_exit,
) -> Decimal:
    """
    Compute IL between two PoolHistoryPoint records using the pool's
    internal price series (price_token1_in_token0).

    Uses price_token1_in_token0 consistently on both records.
    Returns Decimal <= 0.
    Raises ValueError if either record has zero price.
    """
    k = price_ratio(
        price_exit=pool_record_exit.price_token1_in_token0,
        price_entry=pool_record_entry.price_token1_in_token0,
    )
    return impermanent_loss(k)


def il_from_token_prices(
    token0_price_entry: Decimal,
    token0_price_exit: Decimal,
    token1_price_entry: Decimal,
    token1_price_exit: Decimal,
) -> Decimal:
    """
    Compute IL from independent USD token prices.

    Derives price ratio as (token0_usd / token1_usd) at entry and exit.
    Raises ValueError if any price is zero.
    """
    if token1_price_entry == ZERO or token1_price_exit == ZERO:
        raise ValueError("token1 prices must be non-zero")
    if token0_price_entry == ZERO or token0_price_exit == ZERO:
        raise ValueError("token0 prices must be non-zero")

    ratio_entry = token0_price_entry / token1_price_entry
    ratio_exit = token0_price_exit / token1_price_exit
    k = price_ratio(ratio_exit, ratio_entry)
    return impermanent_loss(k)