"""Pool scoring engine — ranks pools by composite LP attractiveness."""
# AUDIT:status=partial
# AUDIT:sprint=1
# AUDIT:issue=score() and rank_pools() accept raw dict instead of PoolDayData
# AUDIT:issue=Hardcoded default weights should come from config/default.yaml
# AUDIT:issue=All financial params use float instead of Decimal

from __future__ import annotations


class PoolScorer:
    """Wrapper class for pool scoring with config-backed weights."""

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or {
            "net_lp_alpha_30d": 0.50,
            "annualized_vol_30d": -0.20,
            "fee_apr": 0.20,
            "volume_tvl_ratio": -0.10,
        }

    def normalize(self, value: float, min_val: float, max_val: float) -> float:
        """Min-max normalize a value to [0, 1]. Returns 0.5 when range is zero."""
        if max_val == min_val:
            return 0.5
        return max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))

    def score(self, pool_data: dict) -> float:
        """Score a single pool dict. Returns 0.0 when data is empty."""
        if not pool_data:
            return 0.0
        return compute_pool_score(
            net_lp_alpha_30d=pool_data.get("net_lp_alpha_30d", 0.0),
            annualized_vol_30d=pool_data.get("annualized_vol_30d", 0.0),
            fee_apr=pool_data.get("fee_apr", 0.0),
            volume_tvl_ratio=pool_data.get("volume_tvl_ratio", 0.0),
            weights=self.weights,
        )


def compute_pool_score(
    net_lp_alpha_30d: float,
    annualized_vol_30d: float,
    fee_apr: float,
    volume_tvl_ratio: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute a weighted composite score for a pool.

    Default weights from config:
        net_lp_alpha_30d:  0.50   (higher is better)
        annualized_vol_30d: -0.20 (lower vol is better, hence negative weight)
        fee_apr:           0.20   (higher APR is better)
        volume_tvl_ratio:  -0.10  (lower turnover preferred for stability)

    Args:
        net_lp_alpha_30d:   Net LP alpha over last 30 days.
        annualized_vol_30d: Annualized volatility over last 30 days.
        fee_apr:            Current annualized fee APR.
        volume_tvl_ratio:   Volume / TVL ratio for the period.
        weights:            Optional override of default weights.

    Returns:
        Composite score (higher = more attractive pool).
    """
    if weights is None:
        weights = {
            "net_lp_alpha_30d": 0.50,
            "annualized_vol_30d": -0.20,
            "fee_apr": 0.20,
            "volume_tvl_ratio": -0.10,
        }

    score = (
        weights["net_lp_alpha_30d"] * net_lp_alpha_30d
        + weights["annualized_vol_30d"] * annualized_vol_30d
        + weights["fee_apr"] * fee_apr
        + weights["volume_tvl_ratio"] * volume_tvl_ratio
    )

    return score


def hard_gate_alpha(
    net_lp_alpha_30d: float,
    enabled: bool = True,
) -> bool:
    """Hard filter: reject pools with negative 30-day net LP alpha.

    When enabled, only pools with net_lp_alpha_30d >= 0 pass the gate.

    Args:
        net_lp_alpha_30d: Net LP alpha over last 30 days.
        enabled:          Whether the hard gate is active.

    Returns:
        True if the pool passes the gate (or gate is disabled).
    """
    if not enabled:
        return True
    return net_lp_alpha_30d >= 0


def classify_risk_tier(
    annualized_vol: float,
    fee_apr: float,
    tiers: dict | None = None,
) -> str:
    """Classify a pool into a risk tier based on volatility and fee APR.

    Default tiers from config:
        anchor:      vol <= 0.40, fee_apr >= 0.08
        satellite:   vol <= 0.80, fee_apr >= 0.15
        speculative: fee_apr >= 0.25 (no vol cap)

    Args:
        annualized_vol: Annualized volatility of the pool.
        fee_apr:        Current fee APR.
        tiers:          Optional override of tier definitions.

    Returns:
        Tier name string: "anchor", "satellite", or "speculative".
    """
    if tiers is None:
        tiers = {
            "anchor": {"max_vol": 0.40, "min_fee_apr": 0.08},
            "satellite": {"max_vol": 0.80, "min_fee_apr": 0.15},
            "speculative": {"min_fee_apr": 0.25},
        }

    anchor = tiers.get("anchor", {})
    if (
        annualized_vol <= anchor.get("max_vol", float("inf"))
        and fee_apr >= anchor.get("min_fee_apr", 0)
    ):
        return "anchor"

    satellite = tiers.get("satellite", {})
    if (
        annualized_vol <= satellite.get("max_vol", float("inf"))
        and fee_apr >= satellite.get("min_fee_apr", 0)
    ):
        return "satellite"

    speculative = tiers.get("speculative", {})
    if fee_apr >= speculative.get("min_fee_apr", 0):
        return "speculative"

    return "unclassified"


def rank_pools(
    pools: list[dict],
    weights: dict[str, float] | None = None,
    hard_gate: bool = True,
) -> list[tuple[str, float]]:
    """Score and rank a list of pool metric dicts.

    Each pool dict should have keys matching the scorer parameters:
        net_lp_alpha_30d, annualized_vol_30d, fee_apr, volume_tvl_ratio, pool_id

    Args:
        pools:      List of pool metric dictionaries.
        weights:    Optional weight override.
        hard_gate:  Whether to apply the alpha hard gate.

    Returns:
        Sorted list of (pool_id, score) tuples, highest score first.
    """
    scored: list[tuple[str, float]] = []

    for pool in pools:
        if hard_gate and not hard_gate_alpha(pool.get("net_lp_alpha_30d", -1), enabled=True):
            continue

        score = compute_pool_score(
            net_lp_alpha_30d=pool.get("net_lp_alpha_30d", 0.0),
            annualized_vol_30d=pool.get("annualized_vol_30d", 0.0),
            fee_apr=pool.get("fee_apr", 0.0),
            volume_tvl_ratio=pool.get("volume_tvl_ratio", 0.0),
            weights=weights,
        )

        pool_id = pool.get("pool_id", "unknown")
        scored.append((pool_id, score))

    # Sort by score descending
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored