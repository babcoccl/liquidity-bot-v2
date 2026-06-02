"""Fee tracking and accumulation utilities."""

from __future__ import annotations


class FeeAccumulator:
    """Track cumulative fees earned by a position."""

    def __init__(self):
        self.total_earned: float = 0.0
        self.history: list[float] = []

    def add(self, amount: float) -> None:
        """Add a fee payment to the accumulator. Ignores negative amounts."""
        if amount < 0:
            return
        self.total_earned += amount
        self.history.append(amount)

    def reset(self) -> None:
        """Reset all tracked fees."""
        self.total_earned = 0.0
        self.history.clear()


def compute_fee_apr(
    fees_earned_usd: float,
    deposit_value_usd: float,
    days_elapsed: float,
) -> float:
    """Annualize fee earnings to an APR."""
    if deposit_value_usd <= 0 or days_elapsed <= 0:
        return 0.0
    daily_rate = fees_earned_usd / deposit_value_usd / days_elapsed
    return daily_rate * 365


def estimate_hourly_fees(
    tvl: float,
    volume_24h: float,
    fee_bps: float,
) -> float:
    """Estimate hourly fees for a position based on pool metrics.

    Args:
        tvl:         Total value locked in the pool.
        volume_24h:  24-hour trading volume.
        fee_bps:     Fee tier in basis points (e.g., 50 = 0.5%).
    """
    if tvl <= 0:
        return 0.0
    daily_fees = volume_24h * (fee_bps / 10_000)
    return daily_fees / 24


def lp_fee_share(
    position_value: float,
    pool_tvl: float,
    total_fees_collected: float,
) -> float:
    """Return the LP's proportional share of fees collected.

    Args:
        position_value:         USD value of this position.
        pool_tvl:               Total value locked in the pool.
        total_fees_collected:   Fees earned by the pool in this period.
    """
    if pool_tvl <= 0:
        return 0.0
    share = position_value / pool_tvl
    return share * total_fees_collected


def fee_gas_ratio(
    fees_usd: float,
    gas_cost_usd: float,
) -> float:
    """Return ratio of fees earned to gas spent."""
    if gas_cost_usd <= 0:
        return float("inf")
    return fees_usd / gas_cost_usd
