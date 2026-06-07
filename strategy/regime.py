"""REGIME. CLASSIFY MARKET. TELL STRATEGY HOW DANGEROUS. DECIMAL ONLY. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=17
# AUDIT:issue=none

from __future__ import annotations

from decimal import Decimal

_D = Decimal

# DEFAULT THRESHOLD. COME FROM config/default.yaml regime section.
_DEFAULT_VOL_LOW  = _D("0.20")
_DEFAULT_VOL_HIGH = _D("0.60")
_DEFAULT_TREND    = _D("0.30")
_DEFAULT_BASE_WIDTH = _D("0.10")
_DEFAULT_ALLOC_MULTIPLIERS: dict[str, Decimal] = {
    "low_vol_no_trend":  _D("1.2"),
    "low_vol_trend":     _D("1.0"),
    "high_vol_no_trend": _D("0.5"),
    "high_vol_trend":    _D("0.8"),
}


class RegimeClassifier:
    """REGIME CLASSIFIER. LOOK AT VOL AND TREND. CLASSIFY MARKET."""

    def __init__(
        self,
        vol_threshold_low: Decimal = _DEFAULT_VOL_LOW,
        vol_threshold_high: Decimal = _DEFAULT_VOL_HIGH,
        trend_threshold: Decimal = _DEFAULT_TREND,
    ):
        self.vol_threshold_low = vol_threshold_low
        self.vol_threshold_high = vol_threshold_high
        self.trend_threshold = trend_threshold

    def classify(self, volatility: Decimal, trend: Decimal) -> str:
        """RETURN REGIME STRING."""
        return classify_regime(
            volatility,
            abs(trend),
            self.vol_threshold_low,
            self.vol_threshold_high,
            self.trend_threshold,
        )


def classify_regime(
    volatility: Decimal,
    trend_strength: Decimal,
    vol_threshold_low: Decimal = _DEFAULT_VOL_LOW,
    vol_threshold_high: Decimal = _DEFAULT_VOL_HIGH,
    trend_threshold: Decimal = _DEFAULT_TREND,
) -> str:
    """CLASSIFY REGIME. FOUR POSSIBLE. RETURN STRING.

    low_vol_no_trend  — CALM MARKET. WIDE RANGE GOOD.
    low_vol_trend     — CALM BUT MOVING. WATCH DIRECTION.
    high_vol_no_trend — CHAOS. REDUCE EXPOSURE.
    high_vol_trend    — STRONG MOVE WITH VOL. TIGHT RANGE FOLLOW TREND.
    """
    is_high_vol = volatility >= vol_threshold_high
    is_trending = trend_strength >= trend_threshold

    if is_high_vol and is_trending:
        return "high_vol_trend"
    if is_high_vol:
        return "high_vol_no_trend"
    if is_trending:
        return "low_vol_trend"
    return "low_vol_no_trend"


def optimal_range_width(
    regime: str,
    current_vol: Decimal,
    base_width: Decimal = _DEFAULT_BASE_WIDTH,
) -> Decimal:
    """SUGGEST RANGE WIDTH. REGIME DECIDE. WIDER WHEN CALM. TIGHTER WHEN TRENDING."""
    if regime == "low_vol_no_trend":
        return max(_D("0.05"), base_width * _D("1.5"))
    if regime == "low_vol_trend":
        return max(_D("0.05"), base_width)
    if regime == "high_vol_no_trend":
        return max(_D("0.10"), base_width * _D("2.5"))
    if regime == "high_vol_trend":
        return max(_D("0.03"), base_width * _D("0.6"))
    return base_width


def allocation_adjustment(
    regime: str,
    base_allocation: Decimal,
    multipliers: dict[str, Decimal] | None = None,
) -> Decimal:
    """ADJUST ALLOCATION BY REGIME. CALM MARKET GET MORE. CHAOS GET LESS."""
    m = multipliers if multipliers is not None else _DEFAULT_ALLOC_MULTIPLIERS
    multiplier = m.get(regime, _D("1.0"))
    return min(_D("1.0"), base_allocation * multiplier)


def regime_summary(
    volatility: Decimal,
    trend_strength: Decimal,
    base_allocation: Decimal = _D("1.0"),
) -> dict:
    """FULL REGIME ANALYSIS. RETURN DICT WITH ALL RECOMMENDED PARAMS."""
    regime = classify_regime(volatility, trend_strength)
    range_width = optimal_range_width(regime, volatility)
    allocation = allocation_adjustment(regime, base_allocation)

    return {
        "regime": regime,
        "volatility": volatility,
        "trend_strength": trend_strength,
        "recommended_range_width": range_width,
        "adjusted_allocation": allocation,
    }