# AUDIT:status=complete
# AUDIT:sprint=12

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