"""
Fee tracking and accumulation utilities.
All financial values use TaggedDecimal — never float or bare Decimal.
Denomination rules enforced at every function boundary.
"""
# AUDIT:status=complete
# AUDIT:sprint=7

from __future__ import annotations
from decimal import Decimal
from core.units import TaggedDecimal, DenominationError, usd, ratio, bps


class FeeAccumulator:
    """Track cumulative fees earned by a position. All amounts in USD."""

    def __init__(self) -> None:
        self.total_earned: TaggedDecimal = usd("0")
        self.history: list[TaggedDecimal] = []

    def add(self, amount: TaggedDecimal) -> None:
        """Add a fee payment. amount must be USD denomination. Ignores zero or negative."""
        if amount.denom != "USD":
            raise DenominationError(
                f"FeeAccumulator.add() requires USD denomination, got {amount.denom}"
            )
        if amount.value <= 0:
            return
        self.total_earned = self.total_earned + amount
        self.history.append(amount)

    def reset(self) -> None:
        """Reset all tracked fees."""
        self.total_earned = usd("0")
        self.history.clear()


def compute_fee_apr(
    fees_earned_usd: TaggedDecimal,
    deposit_value_usd: TaggedDecimal,
    days_elapsed: TaggedDecimal,
) -> TaggedDecimal:
    """
    Annualize fee earnings to an APR.
    fees_earned_usd: USD
    deposit_value_usd: USD
    days_elapsed: RATIO (dimensionless count of days)
    Returns: RATIO (annualized APR as decimal, e.g. 0.12 = 12%)
    """
    if deposit_value_usd.value <= 0 or days_elapsed.value <= 0:
        return ratio("0")
    daily_rate = fees_earned_usd.value / deposit_value_usd.value / days_elapsed.value
    return ratio(daily_rate * Decimal("365"))


def estimate_daily_fees(
    tvl_usd: TaggedDecimal,
    volume_usd: TaggedDecimal,
    fee_tier_bps: TaggedDecimal,
) -> TaggedDecimal:
    """
    Estimate daily fees for the full pool.
    tvl_usd: USD
    volume_usd: USD (24h volume)
    fee_tier_bps: BPS (e.g. TaggedDecimal(Decimal("100"), "BPS") for 1%)
    Returns: USD
    """
    if tvl_usd.value <= 0:
        return usd("0")
    fee_decimal = fee_tier_bps.value / Decimal("10000")
    return usd(volume_usd.value * fee_decimal)


def lp_fee_share(
    position_value_usd: TaggedDecimal,
    pool_tvl_usd: TaggedDecimal,
    total_fees_usd: TaggedDecimal,
) -> TaggedDecimal:
    """
    Return this LP's proportional share of fees collected.
    All inputs must be USD denomination.
    Returns: USD
    """
    for arg, name in [
        (position_value_usd, "position_value_usd"),
        (pool_tvl_usd, "pool_tvl_usd"),
        (total_fees_usd, "total_fees_usd"),
    ]:
        if arg.denom != "USD":
            raise DenominationError(
                f"lp_fee_share(): {name} must be USD denomination, got {arg.denom}"
            )
    if pool_tvl_usd.value <= 0:
        return usd("0")
    share = position_value_usd.value / pool_tvl_usd.value
    return usd(share * total_fees_usd.value)


def fee_gas_ratio(
    fees_usd: TaggedDecimal,
    gas_cost_usd: TaggedDecimal,
) -> TaggedDecimal:
    """
    Return ratio of fees earned to gas spent.
    Both inputs must be USD denomination.
    Returns: RATIO
    """
    for arg, name in [(fees_usd, "fees_usd"), (gas_cost_usd, "gas_cost_usd")]:
        if arg.denom != "USD":
            raise DenominationError(
                f"fee_gas_ratio(): {name} must be USD denomination, got {arg.denom}"
            )
    if gas_cost_usd.value <= 0:
        return ratio("0")  # gas_cost of 0 is treated as no cost — return 0 not inf
    return ratio(fees_usd.value / gas_cost_usd.value)