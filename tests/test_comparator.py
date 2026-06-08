"""TEST comparator module. DECIMAL ONLY. NO FILE IO — BUILD OBJECT DIRECT."""
# AUDIT:status=complete
# AUDIT:sprint=20

import pytest
from decimal import Decimal

from reporting.comparator import (
    AggregateStats,
    PoolResult,
    RunSummary,
    compare_runs,
    load_run_summary,
)


def _make_pool_result(**kw):
    """HELPER. MAKE PoolResult WITH DEFAULT."""
    defaults = {
        "pool_address": "0xabc",
        "pair_name": "WETH/USDC",
        "risk_tier": "anchor",
        "entry_score": Decimal("0.5"),
        "net_lp_alpha": Decimal("0.03"),
        "fee_apr": Decimal("0.18"),
        "il_cost": Decimal("-0.005"),
        "total_fees_earned": Decimal("300"),
        "hours_simulated": 480,
        "exit_reason": "MAX_HOLD_EXCEEDED",
        "final_capital": Decimal("10300"),
    }
    defaults.update(kw)
    return PoolResult(**defaults)


def _make_run_summary(pools, **kw):
    """HELPER. MAKE RunSummary WITH DEFAULT."""
    defaults = {
        "schema_version": 1,
        "run_id": "run_001",
        "timestamp": "2026-06-07T20:00:00Z",
        "config_snapshot": {"days": "90"},
        "aggregate": AggregateStats(
            pools_evaluated=5,
            pools_simulated=4,
            pools_skipped_entry_gate=1,
            mean_net_lp_alpha=Decimal("0.03"),
            median_net_lp_alpha=Decimal("0.028"),
            total_fees_earned=Decimal("1200"),
            mean_fee_apr=Decimal("0.18"),
            mean_hours_simulated=Decimal("400"),
            most_common_exit_reason="MAX_HOLD_EXCEEDED",
            exit_reason_counts={"MAX_HOLD_EXCEEDED": 3},
        ),
        "pools": pools,
    }
    defaults.update(kw)
    return RunSummary(**defaults)


# ---------- compare_runs tests ----------

def test_compare_runs_returns_run_delta():
    a = _make_run_summary([_make_pool_result()])
    b = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.04"))])
    delta = compare_runs(a, b)
    assert delta.run_id_a == "run_001"
    assert len(delta.pool_deltas) == 1


def test_compare_runs_mean_alpha_delta_correct():
    a = _make_run_summary(
        [_make_pool_result()],
        aggregate=AggregateStats(
            pools_evaluated=1, pools_simulated=1, pools_skipped_entry_gate=0,
            mean_net_lp_alpha=Decimal("0.02"), median_net_lp_alpha=Decimal("0.02"),
            total_fees_earned=Decimal("200"), mean_fee_apr=Decimal("0.15"),
            mean_hours_simulated=Decimal("480"), most_common_exit_reason="MAX_HOLD_EXCEEDED",
            exit_reason_counts={"MAX_HOLD_EXCEEDED": 1},
        ),
    )
    b = _make_run_summary(
        [_make_pool_result()],
        aggregate=AggregateStats(
            pools_evaluated=1, pools_simulated=1, pools_skipped_entry_gate=0,
            mean_net_lp_alpha=Decimal("0.04"), median_net_lp_alpha=Decimal("0.04"),
            total_fees_earned=Decimal("400"), mean_fee_apr=Decimal("0.20"),
            mean_hours_simulated=Decimal("480"), most_common_exit_reason="MAX_HOLD_EXCEEDED",
            exit_reason_counts={"MAX_HOLD_EXCEEDED": 1},
        ),
    )
    delta = compare_runs(a, b)
    assert delta.mean_alpha_delta > Decimal("0")


def test_compare_runs_improved_pool_status():
    a = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.02"))])
    b = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.04"))])
    delta = compare_runs(a, b)
    assert delta.pool_deltas[0].status == "improved"


def test_compare_runs_degraded_pool_status():
    a = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.05"))])
    b = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.02"))])
    delta = compare_runs(a, b)
    assert delta.pool_deltas[0].status == "degraded"


def test_compare_runs_unchanged_pool_status():
    a = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.03"))])
    b = _make_run_summary([_make_pool_result(net_lp_alpha=Decimal("0.0305"))])
    delta = compare_runs(a, b)
    assert delta.pool_deltas[0].status == "unchanged"


def test_compare_runs_added_pool():
    a = _make_run_summary([])
    p = _make_pool_result(pool_address="0xnew", pair_name="NEW/TOKEN")
    b = _make_run_summary([p])
    delta = compare_runs(a, b)
    assert len(delta.pool_deltas) == 1
    d = delta.pool_deltas[0]
    assert d.status == "added"
    assert d.net_lp_alpha_a == Decimal("0")


def test_compare_runs_dropped_pool():
    p = _make_pool_result(pool_address="0xold", pair_name="OLD/TOKEN")
    a = _make_run_summary([p])
    b = _make_run_summary([])
    delta = compare_runs(a, b)
    assert len(delta.pool_deltas) == 1
    d = delta.pool_deltas[0]
    assert d.status == "dropped"
    assert d.net_lp_alpha_b == Decimal("0")


def test_compare_runs_does_not_raise_on_empty_pools():
    a = _make_run_summary([])
    b = _make_run_summary([])
    delta = compare_runs(a, b)
    assert delta.pool_deltas == []


def test_compare_runs_pools_skipped_delta_correct():
    agg_a = AggregateStats(
        pools_evaluated=10, pools_simulated=6, pools_skipped_entry_gate=4,
        mean_net_lp_alpha=Decimal("0.03"), median_net_lp_alpha=Decimal("0.03"),
        total_fees_earned=Decimal("300"), mean_fee_apr=Decimal("0.15"),
        mean_hours_simulated=Decimal("400"), most_common_exit_reason="MAX_HOLD_EXCEEDED",
        exit_reason_counts={"ENTRY_SCORE_BELOW_THRESHOLD": 4},
    )
    agg_b = AggregateStats(
        pools_evaluated=10, pools_simulated=8, pools_skipped_entry_gate=2,
        mean_net_lp_alpha=Decimal("0.03"), median_net_lp_alpha=Decimal("0.03"),
        total_fees_earned=Decimal("400"), mean_fee_apr=Decimal("0.15"),
        mean_hours_simulated=Decimal("400"), most_common_exit_reason="MAX_HOLD_EXCEEDED",
        exit_reason_counts={"ENTRY_SCORE_BELOW_THRESHOLD": 2},
    )
    a = _make_run_summary([], aggregate=agg_a)
    b = _make_run_summary([], aggregate=agg_b)
    delta = compare_runs(a, b)
    assert delta.pools_skipped_delta == -2


# ---------- load_run_summary tests ----------

def test_load_run_summary_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        load_run_summary("nonexistent_run_999")