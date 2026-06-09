"""
Evaluator — assesses open positions against exit criteria.

evaluate_position() is the primary entry point for the strategy layer.
All inputs are typed. Returns ExitSignal.
"""
# AUDIT:status=complete
# AUDIT:sprint=13

from decimal import Decimal

from core.il import tick_to_price
from core.models import PoolHistoryPoint, TokenHistoryPoint
from strategy.exit_signal import ExitReason, ExitSignal
from strategy.il_calculator import il_from_token_prices
from strategy.position import Position


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
    pool_by_ts = {r.timestamp: r for r in pool_records}
    t0_by_ts   = {r.timestamp: r for r in token0_prices}
    t1_by_ts   = {r.timestamp: r for r in token1_prices}

    common = set(pool_by_ts) & set(t0_by_ts) & set(t1_by_ts)
    return [
        (pool_by_ts[ts], t0_by_ts[ts], t1_by_ts[ts])
        for ts in sorted(common)
    ]


_ONE_HOUR = 3600

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
    def _nearest(records, label):
        if not records:
            raise ValueError(f"find_entry_records: empty {label} list")
        best = min(records, key=lambda r: abs(r.timestamp - entry_timestamp))
        if abs(best.timestamp - entry_timestamp) > _ONE_HOUR:
            raise ValueError(
                f"find_entry_records: no {label} record within ±1 hour of "
                f"{entry_timestamp}; closest was {best.timestamp} "
                f"(delta={abs(best.timestamp - entry_timestamp)}s)"
            )
        return best

    return (
        _nearest(pool_records,  "pool"),
        _nearest(token0_prices, "token0"),
        _nearest(token1_prices, "token1"),
    )


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
    il_current: Decimal = il_from_token_prices(
        token0_price_entry=position.entry_token0_price_usd,
        token0_price_exit=current_token0_price.price_usd,
        token1_price_entry=position.entry_token1_price_usd,
        token1_price_exit=current_token1_price.price_usd,
    )

    def _signal(reason: ExitReason, details: str) -> ExitSignal:
        return ExitSignal(
            triggered=True,
            reason=reason,
            il_current=il_current,
            timestamp=current_pool_record.timestamp,
            details=details,
        )

    # Priority 1: IL threshold
    if il_current <= max_il_pct:
        return _signal(
            ExitReason.IL_THRESHOLD,
            f"IL {il_current:.4%} <= threshold {max_il_pct:.4%}",
        )

    # Priority 2: Price out of range
    price_lower = tick_to_price(position.tick_lower)
    price_upper = tick_to_price(position.tick_upper)
    current_price = current_pool_record.price_token1_in_token0
    if current_price < price_lower or current_price > price_upper:
        return _signal(
            ExitReason.PRICE_OUT_OF_RANGE,
            f"price {current_price} outside range [{price_lower}, {price_upper}] "
            f"(ticks {position.tick_lower}..{position.tick_upper})",
        )

    # Priority 3: TVL floor (skip when tvl=0 means "not available from source")
    if current_pool_record.tvl_usd > Decimal("0") and current_pool_record.tvl_usd < min_tvl_usd:
        return _signal(
            ExitReason.TVL_DECAY,
            f"TVL ${current_pool_record.tvl_usd} < floor ${min_tvl_usd}",
        )

    # Priority 4: Volume floor
    if current_pool_record.volume_usd < min_volume_usd:
        return _signal(
            ExitReason.VOLUME_DECAY,
            f"Volume ${current_pool_record.volume_usd} < floor ${min_volume_usd}",
        )

    # Priority 5: Time limit
    elapsed_hours = (current_pool_record.timestamp - position.entry_timestamp) // 3600
    if elapsed_hours >= max_hold_hours:
        return _signal(
            ExitReason.TIME_LIMIT,
            f"Hold duration {elapsed_hours}h >= max {max_hold_hours}h",
        )

    # No exit triggered
    return ExitSignal(
        triggered=False,
        reason=None,
        il_current=il_current,
        timestamp=current_pool_record.timestamp,
    )