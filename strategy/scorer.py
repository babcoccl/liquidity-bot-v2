"""SCORER. RANK POOL. WEIGHT FROM CONFIG. DECIMAL ONLY. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=17
# AUDIT:issue=none

from __future__ import annotations

from decimal import Decimal


# DEFAULT WEIGHT. COME FROM config/default.yaml scoring.weights.
# CALLER LOAD FROM YAML AND PASS IN. THIS JUST FALLBACK.
_DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "net_lp_alpha_30d": Decimal("0.50"),
    "annualized_vol_30d": Decimal("-0.20"),
    "fee_apr": Decimal("0.20"),
    "volume_tvl_ratio": Decimal("-0.10"),
}

_DEFAULT_TIERS: dict[str, dict[str, Decimal]] = {
    "anchor":      {"max_vol": Decimal("0.40"), "min_fee_apr": Decimal("0.08")},
    "satellite":   {"max_vol": Decimal("0.80"), "min_fee_apr": Decimal("0.15")},
    "speculative": {"min_fee_apr": Decimal("0.25")},
}


class PoolScorer:
    """SCORER CLASS. HOLD WEIGHT. SCORE POOL."""

    def __init__(self, weights: dict[str, Decimal] | None = None):
        self.weights: dict[str, Decimal] = weights or dict(_DEFAULT_WEIGHTS)

    def normalize(self, value: Decimal, min_val: Decimal, max_val: Decimal) -> Decimal:
        """NORMALIZE VALUE TO 0..1. RANGE ZERO RETURN HALF."""
        if max_val == min_val:
            return Decimal("0.5")
        raw = (value - min_val) / (max_val - min_val)
        return max(Decimal("0"), min(Decimal("1"), raw))

    def score(self, pool_data: dict) -> Decimal:
        """SCORE ONE POOL DICT. RETURN ZERO WHEN EMPTY."""
        if not pool_data:
            return Decimal("0")
        return compute_pool_score(
            net_lp_alpha_30d=Decimal(str(pool_data.get("net_lp_alpha_30d", "0"))),
            annualized_vol_30d=Decimal(str(pool_data.get("annualized_vol_30d", "0"))),
            fee_apr=Decimal(str(pool_data.get("fee_apr", "0"))),
            volume_tvl_ratio=Decimal(str(pool_data.get("volume_tvl_ratio", "0"))),
            weights=self.weights,
        )


def compute_pool_score(
    net_lp_alpha_30d: Decimal,
    annualized_vol_30d: Decimal,
    fee_apr: Decimal,
    volume_tvl_ratio: Decimal,
    weights: dict[str, Decimal] | None = None,
    trend_penalty: Decimal = Decimal("0"),
) -> Decimal:
    """COMPUTE SCORE. WEIGHT TIMES VALUE. SUM ALL. SUBTRACT TREND PENALTY. RETURN DECIMAL."""
    w = weights if weights is not None else _DEFAULT_WEIGHTS
    return (
        w["net_lp_alpha_30d"] * net_lp_alpha_30d
        + w["annualized_vol_30d"] * annualized_vol_30d
        + w["fee_apr"] * fee_apr
        + w["volume_tvl_ratio"] * volume_tvl_ratio
        - trend_penalty
    )


def hard_gate_alpha(
    net_lp_alpha_30d: Decimal,
    enabled: bool = True,
) -> bool:
    """GATE. NEGATIVE ALPHA POOL NOT PASS. RETURN TRUE WHEN PASS."""
    if not enabled:
        return True
    return net_lp_alpha_30d >= Decimal("0")


def classify_risk_tier(
    annualized_vol: Decimal,
    fee_apr: Decimal,
    tiers: dict[str, dict[str, Decimal]] | None = None,
) -> str:
    """CLASSIFY TIER. ANCHOR GOOD. SPECULATIVE RISKY. RETURN STRING."""
    t = tiers if tiers is not None else _DEFAULT_TIERS

    anchor = t.get("anchor", {})
    if (
        annualized_vol <= anchor.get("max_vol", Decimal("Inf"))
        and fee_apr >= anchor.get("min_fee_apr", Decimal("0"))
    ):
        return "anchor"

    satellite = t.get("satellite", {})
    if (
        annualized_vol <= satellite.get("max_vol", Decimal("Inf"))
        and fee_apr >= satellite.get("min_fee_apr", Decimal("0"))
    ):
        return "satellite"

    speculative = t.get("speculative", {})
    if fee_apr >= speculative.get("min_fee_apr", Decimal("0")):
        return "speculative"

    return "unclassified"


def rank_pools(
    pools: list[dict],
    weights: dict[str, Decimal] | None = None,
    hard_gate: bool = True,
) -> list[tuple[str, Decimal]]:
    """RANK POOLS. HIGH SCORE FIRST. NEGATIVE ALPHA POOL FILTERED WHEN GATE ON."""
    scored: list[tuple[str, Decimal]] = []

    for pool in pools:
        alpha = Decimal(str(pool.get("net_lp_alpha_30d", "0")))
        if hard_gate and not hard_gate_alpha(alpha, enabled=True):
            continue

        s = compute_pool_score(
            net_lp_alpha_30d=alpha,
            annualized_vol_30d=Decimal(str(pool.get("annualized_vol_30d", "0"))),
            fee_apr=Decimal(str(pool.get("fee_apr", "0"))),
            volume_tvl_ratio=Decimal(str(pool.get("volume_tvl_ratio", "0"))),
            weights=weights,
        )
        scored.append((pool.get("pool_id", "unknown"), s))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored