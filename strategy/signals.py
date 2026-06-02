"""Exit signal detection for LP positions."""
# AUDIT NOTE: All financial params use float instead of Decimal. Hardcoded default thresholds (drawdown 0.15, crash 0.03/hr, tvl_collapse -0.30, il_fee_ratio 8.0, hold_hours 24) should come from config/default.yaml signals section. No PoolDayData usage. No hardcoded addresses.

from __future__ import annotations


class DrawdownSignal:
    """Signal A: triggers when price drawdown exceeds threshold."""

    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold

    def check(self, current_price: float, peak_price: float) -> bool:
        """Return True if drawdown from peak >= threshold."""
        return signal_a_drawdown(current_price, peak_price, self.threshold)


def signal_a_drawdown(
    current_value: float,
    peak_value: float,
    threshold_pct: float = 0.15,
) -> bool:
    """Signal A: Pool drawdown exceeds threshold.

    Args:
        current_value:   Current USD value of the position.
        peak_value:      All-time high USD value since entry.
        threshold_pct:   Drawdown threshold (default 15%).

    Returns:
        True if drawdown >= threshold.
    """
    if peak_value <= 0:
        return False
    drawdown = (peak_value - current_value) / peak_value
    return drawdown >= threshold_pct


def signal_b_momentum_crash(
    returns: list[float],
    crash_threshold_per_hr: float = 0.03,
    lookback_hours: int = 3,
) -> bool:
    """Signal B: Negative momentum crash detected.

    Checks if the average hourly return over the lookback window exceeds
    the crash threshold (negative).

    Args:
        returns:              List of recent hourly returns (most recent last).
        crash_threshold_per_hr: Minimum negative return per hour to trigger.
        lookback_hours:       Number of hours to look back.

    Returns:
        True if momentum crash detected.
    """
    if len(returns) < lookback_hours:
        return False

    recent = returns[-lookback_hours:]
    avg_return = sum(recent) / len(recent)

    # Trigger when average hourly return is more negative than threshold
    return avg_return <= -crash_threshold_per_hr


def signal_c_tvl_collapse(
    tvl_current: float,
    tvl_reference: float,
    collapse_rate: float = -0.30,
) -> bool:
    """Signal C: TVL collapse detected.

    Args:
        tvl_current:   Current total value locked in the pool.
        tvl_reference: Reference TVL (e.g., 24h ago or at entry).
        collapse_rate: Threshold rate of change (default -30%).

    Returns:
        True if TVL dropped by >= |collapse_rate|.
    """
    if tvl_reference <= 0:
        return False
    change = (tvl_current - tvl_reference) / tvl_reference
    return change <= collapse_rate


def signal_d_il_fee_ratio(
    il_loss_usd: float,
    fees_earned_usd: float,
    threshold: float = 8.0,
    hold_hours: float = 24.0,
    position_hours: float = 24.0,
) -> bool:
    """Signal D (demoted): IL/Fee ratio too high and minimum hold time passed.

    When IL loss is more than `threshold`x the fees earned AND the position
    has been held for at least `hold_hours`, consider exiting.

    Args:
        il_loss_usd:      Total impermanent loss in USD.
        fees_earned_usd:  Total fees earned in USD.
        threshold:        IL/Fee ratio threshold (default 8.0).
        hold_hours:       Minimum hours to hold before signal activates.
        position_hours:   How long the position has been open.

    Returns:
        True if exit signal triggered.
    """
    if position_hours < hold_hours:
        return False

    if fees_earned_usd <= 0:
        # No fees earned but IL is accumulating — always trigger
        return il_loss_usd > 0

    ratio = il_loss_usd / fees_earned_usd
    return ratio >= threshold


class MomentumCrashSignal:
    """Signal B wrapper: momentum crash detection."""

    def __init__(self, lookback_hrs: int = 3, threshold: float = 0.03):
        self.lookback_hrs = lookback_hrs
        self.threshold = threshold

    def check(self, prices: list[float], now_ts: str | None = None) -> bool:
        if len(prices) < 2:
            return False
        returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        return signal_b_momentum_crash(returns, self.threshold, self.lookback_hrs)


class TVLCollapseSignal:
    """Signal C wrapper: TVL collapse detection."""

    def __init__(self, threshold: float = -0.30):
        self.threshold = threshold

    def check(self, current_tvl: float, peak_tvl: float) -> bool:
        return signal_c_tvl_collapse(current_tvl, peak_tvl, self.threshold)


class ILFeeRatioSignal:
    """Signal D wrapper: IL/Fee ratio detection."""

    def __init__(self, threshold: float = 8.0):
        self.threshold = threshold

    def check(self, il_loss_pct: float, fee_apr: float) -> bool:
        # Simplified: trigger when il_loss_pct / fee_apr >= threshold
        if fee_apr <= 0:
            return False
        return (il_loss_pct / fee_apr) >= self.threshold


def any_exit_signal(
    current_value: float,
    peak_value: float,
    hourly_returns: list[float],
    tvl_current: float,
    tvl_reference: float,
    il_loss_usd: float,
    fees_earned_usd: float,
    position_hours: float = 24.0,
    cfg: dict | None = None,
) -> list[str]:
    """Evaluate all exit signals and return list of triggered signal names.

    Args:
        current_value:   Current position value.
        peak_value:      Peak position value.
        hourly_returns:  Recent hourly returns.
        tvl_current:     Current pool TVL.
        tvl_reference:   Reference pool TVL.
        il_loss_usd:     Accumulated IL loss.
        fees_earned_usd: Accumulated fee earnings.
        position_hours:  Hours since position opened.
        cfg:             Optional config dict with signal thresholds.

    Returns:
        List of triggered signal names (e.g., ["drawdown", "momentum_crash"]).
    """
    if cfg is None:
        cfg = {}

    signals_triggered: list[str] = []

    if signal_a_drawdown(
        current_value, peak_value,
        threshold_pct=cfg.get("drawdown_pct", 0.15),
    ):
        signals_triggered.append("drawdown")

    if signal_b_momentum_crash(
        hourly_returns,
        crash_threshold_per_hr=cfg.get("momentum_crash_pct_per_hr", 0.03),
        lookback_hours=cfg.get("momentum_crash_lookback_hrs", 3),
    ):
        signals_triggered.append("momentum_crash")

    if signal_c_tvl_collapse(
        tvl_current, tvl_reference,
        collapse_rate=cfg.get("tvl_collapse_rate", -0.30),
    ):
        signals_triggered.append("tvl_collapse")

    if signal_d_il_fee_ratio(
        il_loss_usd, fees_earned_usd,
        threshold=cfg.get("il_fee_ratio_threshold", 8.0),
        hold_hours=cfg.get("il_fee_min_hold_hours", 24.0),
        position_hours=position_hours,
    ):
        signals_triggered.append("il_fee_ratio")

    return signals_triggered