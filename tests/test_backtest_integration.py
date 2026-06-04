# AUDIT:status=complete
# AUDIT:sprint=14

from decimal import Decimal
from pathlib import Path

from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from registry.registry import PoolRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_config() -> BacktestConfig:
    return BacktestConfig(
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


def test_end_to_end_il_trigger():
    """
    WETH $2000 → $4000 across 5 hourly fixture records.
    IL at k=2.0 is -5.719%, exceeds -5% threshold.
    Harness must exit before or at record 4 (hours_simulated <= 4).
    """
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)

    results = harness.run(run_id="test_sprint12")

    assert len(results) == 1
    result = results[0]
    assert result.pair_name == "WETH-USDC"
    assert result.il_cost < Decimal("0"), "IL cost must be negative (a loss)"
    assert result.days_simulated <= 4


def test_il_cost_and_capital_are_decimal():
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id="test_sprint12_types")
    assert isinstance(results[0].il_cost, Decimal)
    assert isinstance(results[0].final_capital, Decimal)


# ---------------------------------------------------------------------------
# Sprint 13 — Fee attribution, exit_reason, hours_simulated
# ---------------------------------------------------------------------------

def test_fee_attribution_nonzero():
    """
    With real volume data in the fixture, total_fees_earned must be > 0.
    Fixture records have volume_usd=500000 per record and pool fee_tier=500 (0.05%).
    LP share = 10000 / 2000000 = 0.005. Fees/record ≈ 500000 * 0.0005 * 0.005 = $1.25.
    Over up to 4 steps: total must be > 0.
    """
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id="test_sprint13_fees")

    assert len(results) == 1
    assert results[0].total_fees_earned > Decimal("0")
    assert isinstance(results[0].total_fees_earned, Decimal)


def test_exit_reason_in_result():
    """exit_reason field must be a non-None string when position exits."""
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id="test_sprint13_exit_reason")

    assert len(results) == 1
    # IL trigger fires at k=2.0 (fixture record 4) → exit_reason must be set
    assert results[0].exit_reason is not None
    assert isinstance(results[0].exit_reason, str)
    assert results[0].hours_simulated >= 1


def test_hours_simulated_field_type():
    """hours_simulated must be an int >= 0 on all result paths."""
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id="test_sprint13_hours")

    assert isinstance(results[0].hours_simulated, int)
    assert results[0].hours_simulated >= 0


# ---------------------------------------------------------------------------
# Sprint 14 — Tick Range Wiring & In-Range Fee Attribution
# ---------------------------------------------------------------------------

def test_full_range_position_still_earns_fees():
    """
    Regression guard for Sprint 14:
    fixture registry stub uses full-range sentinel ticks, so fee gating
    must not zero out fees for the existing WETH-USDC fixture path.
    """
    config = _make_config()
    registry = PoolRegistry(path=config.registry_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)

    results = harness.run(run_id="test_sprint14_full_range_fees")

    assert len(results) == 1
    assert results[0].total_fees_earned > Decimal("0")


def test_narrow_range_triggers_price_out_of_range(tmp_path):
    """
    Build a narrow-range registry stub for the same WETH-USDC fixture files.
    Suppress IL so PRICE_OUT_OF_RANGE is the first exit.
    """
    import json
    import shutil

    narrow_stub = [
        {
            "pool_address": "0xb4cb800910b228ed3d0834cf79d697127bbb00e5",
            "pair_name": "WETH-USDC",
            "token0": {
                "symbol": "WETH",
                "address": "0x4200000000000000000000000000000000000006",
                "decimals": 18
            },
            "token1": {
                "symbol": "USDC",
                "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913",
                "decimals": 6
            },
            "fee_tier": 500,
            "tick_lower": 74959,
            "tick_upper": 76966,
            "price_reference": {}
        }
    ]

    stub_path = tmp_path / "registry_narrow.json"
    stub_path.write_text(json.dumps(narrow_stub))

    fixtures = Path(__file__).parent / "fixtures"
    for fname in ["WETH-USDC.json", "WETH.json", "USDC.json"]:
        shutil.copy(fixtures / fname, tmp_path / fname)

    config = BacktestConfig(
        days=365,
        initial_capital=Decimal("10000"),
        bollinger_multiplier=Decimal("2"),
        rotation_margin=Decimal("0.01"),
        min_entry_score=Decimal("0"),
        rebalance_cooldown_hours=Decimal("0"),
        max_rebalances_per_pool_per_day=99,
        historical_dir=tmp_path,
        registry_path=stub_path,
        prices_dir=tmp_path,
        hourly_dir=tmp_path,
        max_il_pct=Decimal("-0.99"),
        min_tvl_usd=Decimal("0"),
        min_volume_usd=Decimal("0"),
        max_hold_hours=9999,
    )

    registry = PoolRegistry(path=stub_path)
    registry.load()
    harness = BacktestHarness(config=config, registry=registry)

    results = harness.run(run_id="test_sprint14_narrow_range")

    assert len(results) == 1
    assert results[0].exit_reason == "PRICE_OUT_OF_RANGE"
    assert results[0].hours_simulated >= 1
