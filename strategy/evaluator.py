"""
Evaluator — assesses open positions against exit criteria.

evaluate_position() is the primary entry point for the strategy layer.
All inputs are typed. Returns ExitSignal.

STUB: bodies not yet implemented. Sprint 12.
"""
# AUDIT:status=stub
# AUDIT:sprint=11

from decimal import Decimal

from core.models import PoolHistoryPoint, TokenHistoryPoint
from strategy.exit_signal import ExitReason, ExitSignal
from strategy.il_calculator import il_from_token_prices
from strategy.position import Position


def evaluate_position(
    position: Position,
    current_pool_record: PoolHistoryPoint,
    current_token0_price: TokenHistoryPoint,
    current_token1_price: TokenHistoryPoint,
    max_il_pct: Decimal = Decimal("-0.05"),
    min_tvl_usd: Decimal = Decimal("500000"),
    min_volume_usd: Decimal = Decimal("50000"),
    max_hold_hours: int = 720,
) -> ExitSignal:
    """
    Evaluate whether a position should be exited at the current timestamp.

    Args:
        position: Entry snapshot (immutable).
        current_pool_record: PoolHistoryPoint at current evaluation time.
        current_token0_price: TokenHistoryPoint for token0 at current time.
        current_token1_price: TokenHistoryPoint for token1 at current time.
        max_il_pct: IL threshold triggering exit (negative, e.g. -0.05 = -5%).
        min_tvl_usd: TVL floor below which exit is triggered.
        min_volume_usd: 24h volume floor below which exit is triggered.
        max_hold_hours: Maximum hours to hold before forced exit.

    Returns:
        ExitSignal with triggered=True and reason if any criterion is met,
        or triggered=False with il_current populated if no exit triggered.
    """
    raise NotImplementedError("evaluate_position: Sprint 12")


def find_entry_records(
    pool_records: list[PoolHistoryPoint],
    token0_prices: list[TokenHistoryPoint],
    token1_prices: list[TokenHistoryPoint],
    entry_timestamp: int,
) -> tuple[PoolHistoryPoint, TokenHistoryPoint, TokenHistoryPoint]:
    """
    Locate the pool and token price records closest to entry_timestamp.

    Raises ValueError if no record within 1 hour of entry_timestamp.
    """
    raise NotImplementedError("find_entry_records: Sprint 12")


def join_records(
    pool_records: list[PoolHistoryPoint],
    token0_prices: list[TokenHistoryPoint],
    token1_prices: list[TokenHistoryPoint],
) -> list[tuple[PoolHistoryPoint, TokenHistoryPoint, TokenHistoryPoint]]:
    """
    Inner-join pool records with token0 and token1 price records on
    timestamp. Returns only timestamps present in all three series.

    Used by backtester to iterate aligned records.
    """
    raise NotImplementedError("join_records: Sprint 12")