"""Market regime classification for adaptive strategy parameters."""
# AUDIT:status=partial
# AUDIT:sprint=1
# AUDIT:issue=Hardcoded default thresholds should come from config/default.yaml
# AUDIT:issue=All financial params use float instead of Decimal

from __future__ import annotations


class RegimeClassifier:
    """Classify market regime based on volatility and trend strength."""

    def __init__(
        self,
        vol_threshold_low: float = 0.20,
        vol_threshold_high: float = 0.60,
        trend_threshold: float = 0.30,
    ):
        self.vol_threshold_low = vol_threshold_low
        self.vol_threshold_high = vol_threshold_high
        self.trend_threshold = trend_threshold

    def classify(self, volatility: float, trend: float) -> str:
        """Return regime string for given volatility and trend."""
        return classify_regime(
            volatility,
            abs(trend),
            self.vol_threshold_low,
            self.vol_threshold_high,
            self.trend_threshold,
        )


def classify_regime(
    volatility: float,
    trend_strength: float,
    vol_threshold_low: float = 0.20,
    vol_threshold_high: float = 0.60,
    trend_threshold: float = 0.30,
) -> str:
    """Classify the current market regime based on volatility and trend.

    Regimes:
        "low_vol_no_trend"  — Range-bound, low vol → wide ranges optimal
        "low_vol_trend"     — Low vol but trending → directional bias
        "high_vol_no_trend" — Chaotic, high vol → reduce exposure
        "high_vol_trend"    — Strong trend with vol → tight ranges in trend direction

    Args:
        volatility:         Current annualized volatility.
        trend_strength:     Absolute value of normalized trend indicator (-1 to 1).
        vol_threshold_low:  Upper bound for "low volatility".
        vol_threshold_high: Lower bound for "high volatility".
        trend_threshold:    Minimum trend strength to classify as trending.

    Returns:
        Regime name string.
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
    current_vol: float,
    base_width: float = 0.10,
) -> float:
    """Suggest an optimal liquidity range width based on regime.

    Args:
        regime:       Current market regime string.
        current_vol:  Current annualized volatility.
        base_width:   Base range width percentage (default 10%).

    Returns:
        Suggested range width as a decimal (e.g., 0.20 = ±10% from mid-price).
    """
    if regime == "low_vol_no_trend":
        # Wide range in low vol — stay in-range longer
        return max(0.05, base_width * 1.5)

    if regime == "low_vol_trend":
        # Moderate range with directional bias
        return max(0.05, base_width)

    if regime == "high_vol_no_trend":
        # Very wide or step back — avoid constant out-of-range
        return max(0.10, base_width * 2.5)

    if regime == "high_vol_trend":
        # Tight range following trend direction
        return max(0.03, base_width * 0.6)

    return base_width


def allocation_adjustment(
    regime: str,
    base_allocation: float,
) -> float:
    """Adjust capital allocation based on market regime.

    Args:
        regime:          Current market regime.
        base_allocation: Default allocation fraction for the pool.

    Returns:
        Adjusted allocation fraction (0 to 1).
    """
    multipliers = {
        "low_vol_no_trend": 1.2,     # Increase — favorable conditions
        "low_vol_trend": 1.0,         # Neutral
        "high_vol_no_trend": 0.5,     # Reduce — chaotic market
        "high_vol_trend": 0.8,        # Slight reduce — risky but profitable
    }

    multiplier = multipliers.get(regime, 1.0)
    return min(1.0, base_allocation * multiplier)


def regime_summary(
    volatility: float,
    trend_strength: float,
    base_allocation: float = 1.0,
) -> dict:
    """Generate a complete regime analysis summary.

    Args:
        volatility:       Current annualized volatility.
        trend_strength:   Normalized trend indicator.
        base_allocation:  Default allocation fraction.

    Returns:
        Dict with regime classification and recommended parameters.
    """
    regime = classify_regime(volatility, trend_strength)
    range_width = optimal_range_width(regime, volatility)
    allocation = allocation_adjustment(regime, base_allocation)

    return {
        "regime": regime,
        "volatility": round(volatility, 4),
        "trend_strength": round(trend_strength, 4),
        "recommended_range_width": round(range_width, 4),
        "adjusted_allocation": round(allocation, 4),
    }