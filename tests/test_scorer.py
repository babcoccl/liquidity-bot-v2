"""TEST SCORER. DECIMAL ONLY. WEIGHTS FROM CONFIG. NO FLOAT LEAK."""
# AUDIT:status=complete
# AUDIT:sprint=17

from __future__ import annotations

from decimal import Decimal

import pytest

from strategy.scorer import (
    PoolScorer,
    classify_risk_tier,
    compute_pool_score,
    hard_gate_alpha,
    rank_pools,
)

_D = Decimal


# ── compute_pool_score ────────────────────────────────────────────────

def test_compute_pool_score_returns_decimal():
    result = compute_pool_score(
        net_lp_alpha_30d=_D("0.10"),
        annualized_vol_30d=_D("0.30"),
        fee_apr=_D("0.20"),
        volume_tvl_ratio=_D("0.05"),
    )
    assert isinstance(result, Decimal)


def test_compute_pool_score_zero_inputs_returns_zero():
    result = compute_pool_score(
        net_lp_alpha_30d=_D("0"),
        annualized_vol_30d=_D("0"),
        fee_apr=_D("0"),
        volume_tvl_ratio=_D("0"),
    )
    assert result == _D("0")


def test_compute_pool_score_weight_direction():
    """HIGH NET ALPHA INCREASE SCORE. HIGH VOL DECREASE SCORE."""
    base = compute_pool_score(_D("0"), _D("0"), _D("0"), _D("0"))
    high_alpha = compute_pool_score(_D("1"), _D("0"), _D("0"), _D("0"))
    high_vol = compute_pool_score(_D("0"), _D("1"), _D("0"), _D("0"))
    assert high_alpha > base
    assert high_vol < base


def test_compute_pool_score_custom_weights():
    weights = {
        "net_lp_alpha_30d": _D("1.0"),
        "annualized_vol_30d": _D("0"),
        "fee_apr": _D("0"),
        "volume_tvl_ratio": _D("0"),
    }
    result = compute_pool_score(_D("0.5"), _D("99"), _D("99"), _D("99"), weights=weights)
    assert result == _D("0.5")


def test_compute_pool_score_no_float_in_default_path():
    """DEFAULT WEIGHTS ALL DECIMAL. NO FLOAT LEAK."""
    result = compute_pool_score(_D("0.1"), _D("0.2"), _D("0.3"), _D("0.4"))
    assert isinstance(result, Decimal)


# ── hard_gate_alpha ───────────────────────────────────────────────────

def test_hard_gate_alpha_positive_passes():
    assert hard_gate_alpha(_D("0.01")) is True


def test_hard_gate_alpha_zero_passes():
    assert hard_gate_alpha(_D("0")) is True


def test_hard_gate_alpha_negative_fails():
    assert hard_gate_alpha(_D("-0.01")) is False


def test_hard_gate_alpha_disabled_always_passes():
    assert hard_gate_alpha(_D("-999"), enabled=False) is True


# ── PoolScorer ────────────────────────────────────────────────────────

def test_pool_scorer_default_weights_are_decimal():
    scorer = PoolScorer()
    for k, v in scorer.weights.items():
        assert isinstance(v, Decimal), f"Weight {k} is not Decimal: {type(v)}"


def test_pool_scorer_score_returns_decimal():
    scorer = PoolScorer()
    result = scorer.score({
        "net_lp_alpha_30d": "0.10",
        "annualized_vol_30d": "0.20",
        "fee_apr": "0.15",
        "volume_tvl_ratio": "0.05",
    })
    assert isinstance(result, Decimal)


def test_pool_scorer_score_empty_dict_returns_zero():
    scorer = PoolScorer()
    assert scorer.score({}) == _D("0")


def test_pool_scorer_normalize_returns_decimal():
    scorer = PoolScorer()
    result = scorer.normalize(_D("5"), _D("0"), _D("10"))
    assert isinstance(result, Decimal)
    assert result == _D("0.5")


def test_pool_scorer_normalize_zero_range_returns_half():
    scorer = PoolScorer()
    assert scorer.normalize(_D("5"), _D("5"), _D("5")) == _D("0.5")


def test_pool_scorer_normalize_clamps_to_01():
    scorer = PoolScorer()
    assert scorer.normalize(_D("20"), _D("0"), _D("10")) == _D("1")
    assert scorer.normalize(_D("-5"), _D("0"), _D("10")) == _D("0")


# ── classify_risk_tier ────────────────────────────────────────────────

def test_classify_risk_tier_anchor():
    assert classify_risk_tier(_D("0.30"), _D("0.10")) == "anchor"


def test_classify_risk_tier_satellite():
    assert classify_risk_tier(_D("0.70"), _D("0.20")) == "satellite"


def test_classify_risk_tier_speculative():
    assert classify_risk_tier(_D("0.90"), _D("0.30")) == "speculative"


def test_classify_risk_tier_unclassified():
    assert classify_risk_tier(_D("0.90"), _D("0.01")) == "unclassified"


def test_classify_risk_tier_decimal_inputs_only():
    result = classify_risk_tier(_D("0.3"), _D("0.1"))
    assert isinstance(result, str)


# ── rank_pools ────────────────────────────────────────────────────────

def test_rank_pools_sorted_descending():
    pools = [
        {"pool_id": "A", "net_lp_alpha_30d": "0.05", "annualized_vol_30d": "0.2", "fee_apr": "0.1", "volume_tvl_ratio": "0.1"},
        {"pool_id": "B", "net_lp_alpha_30d": "0.20", "annualized_vol_30d": "0.1", "fee_apr": "0.2", "volume_tvl_ratio": "0.0"},
    ]
    results = rank_pools(pools)
    assert results[0][0] == "B"
    assert results[1][0] == "A"


def test_rank_pools_hard_gate_filters_negative_alpha():
    pools = [
        {"pool_id": "A", "net_lp_alpha_30d": "-0.10", "annualized_vol_30d": "0.0", "fee_apr": "0.0", "volume_tvl_ratio": "0.0"},
        {"pool_id": "B", "net_lp_alpha_30d": "0.10", "annualized_vol_30d": "0.0", "fee_apr": "0.0", "volume_tvl_ratio": "0.0"},
    ]
    results = rank_pools(pools, hard_gate=True)
    pool_ids = [r[0] for r in results]
    assert "A" not in pool_ids
    assert "B" in pool_ids


def test_rank_pools_hard_gate_off_includes_negative():
    pools = [
        {"pool_id": "A", "net_lp_alpha_30d": "-0.10", "annualized_vol_30d": "0.0", "fee_apr": "0.0", "volume_tvl_ratio": "0.0"},
    ]
    results = rank_pools(pools, hard_gate=False)
    assert len(results) == 1


def test_rank_pools_returns_decimal_scores():
    pools = [{"pool_id": "X", "net_lp_alpha_30d": "0.1", "annualized_vol_30d": "0.1", "fee_apr": "0.1", "volume_tvl_ratio": "0.0"}]
    results = rank_pools(pools)
    assert isinstance(results[0][1], Decimal)