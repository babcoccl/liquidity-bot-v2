"""SIGNAL. DETECT BAD THING HAPPEN TO POSITION. DECIMAL ONLY. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=17
# AUDIT:issue=none

from __future__ import annotations

from decimal import Decimal


# DEFAULT THRESHOLD. COME FROM config/default.yaml signals section.
_D = Decimal


class DrawdownSignal:
    """SIGNAL A. PRICE DROP TOO MUCH. TRIGGER EXIT."""

    def __init__(self, threshold: Decimal = _D("0.15")):
        self.threshold = threshold

    def check(self, current_price: Decimal, peak_price: Decimal) -> bool:
        """RETURN TRUE WHEN DRAWDOWN BIG."""
        return signal_a_drawdown(current_price, peak_price, self.threshold)


def signal_a_drawdown(
    current_value: Decimal,
    peak_value: Decimal,
    threshold_pct: Decimal = _D("0.15"),
) -> bool:
    """SIGNAL A. POOL DRAWDOWN EXCEED THRESHOLD. RETURN TRUE WHEN BAD."""
    if peak_value <= _D("0"):
        return False
    drawdown = (peak_value - current_value) / peak_value
    return drawdown >= threshold_pct


def signal_b_momentum_crash(
    returns: list[Decimal],
    crash_threshold_per_hr: Decimal = _D("0.03"),
    lookback_hours: int = 3,
) -> bool:
    """SIGNAL B. PRICE CRASH FAST. CHECK LAST N HOURS RETURN. RETURN TRUE WHEN CRASH."""
    if len(returns) < lookback_hours:
        return False
    recent = returns[-lookback_hours:]
    avg_return = sum(recent, _D("0")) / _D(str(len(recent)))
    return avg_return <= -crash_threshold_per_hr


def signal_c_tvl_collapse(
    tvl_current: Decimal,
    tvl_reference: Decimal,
    collapse_rate: Decimal = _D("-0.30"),
) -> bool:
    """SIGNAL C. TVL DROP TOO MUCH. POOL DYING. RETURN TRUE WHEN COLLAPSE."""
    if tvl_reference <= _D("0"):
        return False
    change = (tvl_current - tvl_reference) / tvl_reference
    return change <= collapse_rate


def signal_d_il_fee_ratio(
    il_loss_usd: Decimal,
    fees_earned_usd: Decimal,
    threshold: Decimal = _D("8.0"),
    hold_hours: Decimal = _D("24.0"),
    position_hours: Decimal = _D("24.0"),
) -> bool:
    """SIGNAL D. IL EAT FEES. RATIO TOO HIGH. RETURN TRUE WHEN BAD."""
    if position_hours < hold_hours:
        return False
    if fees_earned_usd <= _D("0"):
        return il_loss_usd > _D("0")
    return (il_loss_usd / fees_earned_usd) >= threshold


class MomentumCrashSignal:
    """SIGNAL B WRAPPER. MOMENTUM CRASH DETECT."""

    def __init__(self, lookback_hrs: int = 3, threshold: Decimal = _D("0.03")):
        self.lookback_hrs = lookback_hrs
        self.threshold = threshold

    def check(self, prices: list[Decimal], now_ts: str | None = None) -> bool:
        """COMPUTE RETURNS FROM PRICES. CHECK CRASH."""
        if len(prices) < 2:
            return False
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
        ]
        return signal_b_momentum_crash(returns, self.threshold, self.lookback_hrs)


class TVLCollapseSignal:
    """SIGNAL C WRAPPER. TVL COLLAPSE DETECT."""

    def __init__(self, threshold: Decimal = _D("-0.30")):
        self.threshold = threshold

    def check(self, current_tvl: Decimal, peak_tvl: Decimal) -> bool:
        """RETURN TRUE WHEN TVL COLLAPSE."""
        return signal_c_tvl_collapse(current_tvl, peak_tvl, self.threshold)


class ILFeeRatioSignal:
    """SIGNAL D WRAPPER. IL FEE RATIO DETECT."""

    def __init__(self, threshold: Decimal = _D("8.0")):
        self.threshold = threshold

    def check(self, il_loss_pct: Decimal, fee_apr: Decimal) -> bool:
        """SIMPLIFIED CHECK. RETURN TRUE WHEN RATIO TOO HIGH."""
        if fee_apr <= _D("0"):
            return False
        return (il_loss_pct / fee_apr) >= self.threshold


def any_exit_signal(
    current_value: Decimal,
    peak_value: Decimal,
    hourly_returns: list[Decimal],
    tvl_current: Decimal,
    tvl_reference: Decimal,
    il_loss_usd: Decimal,
    fees_earned_usd: Decimal,
    position_hours: Decimal = _D("24.0"),
    cfg: dict | None = None,
) -> list[str]:
    """EVALUATE ALL SIGNAL. RETURN LIST OF TRIGGERED NAMES."""
    if cfg is None:
        cfg = {}

    triggered: list[str] = []

    if signal_a_drawdown(
        current_value, peak_value,
        threshold_pct=_D(str(cfg.get("drawdown_pct", "0.15"))),
    ):
        triggered.append("drawdown")

    if signal_b_momentum_crash(
        hourly_returns,
        crash_threshold_per_hr=_D(str(cfg.get("momentum_crash_pct_per_hr", "0.03"))),
        lookback_hours=int(cfg.get("momentum_crash_lookback_hrs", 3)),
    ):
        triggered.append("momentum_crash")

    if signal_c_tvl_collapse(
        tvl_current, tvl_reference,
        collapse_rate=_D(str(cfg.get("tvl_collapse_rate", "-0.30"))),
    ):
        triggered.append("tvl_collapse")

    if signal_d_il_fee_ratio(
        il_loss_usd, fees_earned_usd,
        threshold=_D(str(cfg.get("il_fee_ratio_threshold", "8.0"))),
        hold_hours=_D(str(cfg.get("il_fee_min_hold_hours", "24.0"))),
        position_hours=position_hours,
    ):
        triggered.append("il_fee_ratio")

    return triggered