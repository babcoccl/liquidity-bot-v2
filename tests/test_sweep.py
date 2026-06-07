"""
Tests for backtest/sweep.py — SweepConfig, SweepResult, SweepRunner.

All tests are self-contained with no network calls and no filesystem side-effects outside tmp_path.

# AUDIT:status=complete
# AUDIT:sprint=17
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Tuple

from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from backtest.sweep import SweepConfig, SweepResult, SweepRunner
from registry.registry import PoolRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_sweep_config(tmp_path: Path, **overrides) -> Tuple[SweepConfig, PoolRegistry]:
    """
    Build a minimal SweepConfig backed by the WETH-USDC fixture files.
    overrides are applied to the parameter dimension lists only.
    """
    base_config = BacktestConfig(
        days=365,
        initial_capital=Decimal("10000"),
        bollinger_multiplier=Decimal("2"),
        rotation_margin=Decimal("0.01"),
        min_entry_score=Decimal("0"),
        rebalance_cooldown_hours=Decimal("0"),
        max_rebalances_per_pool_per_day=99,
        historical_dir=FIXTURES_DIR,
        registry_path=FIXTURES_DIR / "registry_stub.json",
        prices_dir=FIXTURES_DIR,
        hourly_dir=FIXTURES_DIR,
        max_il_pct=Decimal("-0.05"),
        min_tvl_usd=Decimal("100000"),
        min_volume_usd=Decimal("10000"),
        max_hold_hours=720,
    )

    default_dims = {
        "max_il_pct_values": [Decimal("-0.05")],
        "max_hold_hours_values": [720],
        "min_tvl_usd_values": [Decimal("100000")],
        "min_volume_usd_values": [Decimal("10000")],
    }
    default_dims.update(overrides)

    sweep_config = SweepConfig(
        max_il_pct_values=default_dims["max_il_pct_values"],
        max_hold_hours_values=default_dims["max_hold_hours_values"],
        min_tvl_usd_values=default_dims["min_tvl_usd_values"],
        min_volume_usd_values=default_dims["min_volume_usd_values"],
        base_config=base_config,
        output_dir=tmp_path,
    )

    registry = PoolRegistry(path=FIXTURES_DIR / "registry_stub.json")
    registry.load()

    return sweep_config, registry


# ---------------------------------------------------------------------------
# Test 1: SweepResult field types
# ---------------------------------------------------------------------------

def test_sweep_result_fields():
    """Directly construct a SweepResult and assert all fields are accessible with correct types."""
    result = SweepResult(
        run_id="test_run",
        max_il_pct=Decimal("-0.05"),
        max_hold_hours=720,
        min_tvl_usd=Decimal("100000"),
        min_volume_usd=Decimal("10000"),
        pool_count=3,
        total_net_lp_alpha=Decimal("-565.53"),
        avg_net_lp_alpha=Decimal("-188.51"),
        avg_hours_simulated=Decimal("4"),
        exit_reason_counts={"IL_THRESHOLD": 2, "TIME_LIMIT": 1},
    )

    assert isinstance(result.run_id, str)
    assert result.run_id == "test_run"
    assert isinstance(result.max_il_pct, Decimal)
    assert result.max_il_pct == Decimal("-0.05")
    assert isinstance(result.max_hold_hours, int)
    assert result.max_hold_hours == 720
    assert isinstance(result.min_tvl_usd, Decimal)
    assert result.min_tvl_usd == Decimal("100000")
    assert isinstance(result.min_volume_usd, Decimal)
    assert result.min_volume_usd == Decimal("10000")
    assert isinstance(result.pool_count, int)
    assert result.pool_count == 3
    assert isinstance(result.total_net_lp_alpha, Decimal)
    assert result.total_net_lp_alpha == Decimal("-565.53")
    assert isinstance(result.avg_net_lp_alpha, Decimal)
    assert result.avg_net_lp_alpha == Decimal("-188.51")
    assert isinstance(result.avg_hours_simulated, Decimal)
    assert result.avg_hours_simulated == Decimal("4")
    assert isinstance(result.exit_reason_counts, dict)
    assert result.exit_reason_counts == {"IL_THRESHOLD": 2, "TIME_LIMIT": 1}


# ---------------------------------------------------------------------------
# Test 2: Single combination sweep
# ---------------------------------------------------------------------------

def test_sweep_runner_single_combination(tmp_path):
    """Build a SweepConfig with exactly one value in each dimension and run."""
    sweep_config, registry = _make_sweep_config(tmp_path)
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_single")

    assert len(results) == 1
    assert results[0].pool_count == 1


# ---------------------------------------------------------------------------
# Test 3: Cartesian product
# ---------------------------------------------------------------------------

def test_sweep_runner_cartesian_product(tmp_path):
    """2 il × 2 hold × 1 tvl × 1 vol = 4 combinations."""
    sweep_config, registry = _make_sweep_config(
        tmp_path,
        max_il_pct_values=[Decimal("-0.03"), Decimal("-0.05")],
        max_hold_hours_values=[168, 720],
    )
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_cartesian")

    assert len(results) == 4


# ---------------------------------------------------------------------------
# Test 4: Results sorted descending by avg_net_lp_alpha
# ---------------------------------------------------------------------------

def test_sweep_runner_results_sorted_descending(tmp_path):
    """Run a 4-combination sweep and verify descending sort."""
    sweep_config, registry = _make_sweep_config(
        tmp_path,
        max_il_pct_values=[Decimal("-0.03"), Decimal("-0.05")],
        max_hold_hours_values=[168, 720],
    )
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_sorted")

    assert len(results) == 4
    for i in range(len(results) - 1):
        assert results[i].avg_net_lp_alpha >= results[i + 1].avg_net_lp_alpha


# ---------------------------------------------------------------------------
# Test 5: save() writes valid JSON
# ---------------------------------------------------------------------------

def test_sweep_runner_save_writes_json(tmp_path):
    """Run a 1-combination sweep, call save(), and verify the output file."""
    sweep_config, registry = _make_sweep_config(tmp_path)
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_save")
    output_path = runner.save("test_save", results)

    assert output_path.exists()
    data = json.loads(output_path.read_text())
    assert isinstance(data, list)
    assert len(data) == 1

    entry = data[0]
    expected_fields = [
        "run_id", "max_il_pct", "max_hold_hours", "min_tvl_usd",
        "min_volume_usd", "pool_count", "total_net_lp_alpha",
        "avg_net_lp_alpha", "avg_hours_simulated", "exit_reason_counts",
    ]
    for field in expected_fields:
        assert field in entry, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Test 6: exit_reason_counts contains NONE key when no threshold triggers
# ---------------------------------------------------------------------------

def test_sweep_result_exit_reason_counts_none_key(tmp_path):
    """Use suppressed thresholds so the fixture exhausts without triggering IL."""
    sweep_config, registry = _make_sweep_config(
        tmp_path,
        max_il_pct_values=[Decimal("-0.99")],
        max_hold_hours_values=[9999],
    )
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_none_exit")

    assert len(results) == 1
    # The fixture terminates on IL at k=2.0 with standard thresholds (-5%),
    # but with -99% threshold the position won't exit on IL. It may still
    # exit on TIME_LIMIT or data exhaustion producing NONE.
    # At minimum, verify the exit_reason_counts dict is non-empty and has keys.
    assert len(results[0].exit_reason_counts) > 0
    assert "NONE" in results[0].exit_reason_counts, (
        f"Expected 'NONE' key in exit_reason_counts, got: {results[0].exit_reason_counts}"
    )
    assert results[0].exit_reason_counts["NONE"] > 0


# ---------------------------------------------------------------------------
# Test 7: Harness exception produces zero-value SweepResult
# ---------------------------------------------------------------------------

def test_sweep_runner_harness_exception_produces_zero_result(tmp_path, monkeypatch):
    """Monkeypatch BacktestHarness.run to raise RuntimeError and verify graceful handling."""
    def fake_run(self, run_id):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(BacktestHarness, "run", fake_run)

    sweep_config, registry = _make_sweep_config(tmp_path)
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run("test_exception")

    assert len(results) == 1
    failing = results[0]
    assert failing.pool_count == 0
    assert failing.total_net_lp_alpha == Decimal("0")
    assert failing.avg_net_lp_alpha == Decimal("0")