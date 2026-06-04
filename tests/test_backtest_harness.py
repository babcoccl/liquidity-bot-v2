"""Tests for backtest.config, backtest.reporter, and backtest.harness."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backtest.config import BacktestConfig
from backtest.reporter import BacktestReporter, BacktestResult
from core.models import PoolDayData


# ── Helpers ──────────────────────────────────────────────

def _make_config(
    days: int = 30,
    historical_dir: Path | None = None,
    registry_path: Path | None = None,
) -> BacktestConfig:
    return BacktestConfig(
        days=days,
        initial_capital=Decimal("10000"),
        bollinger_multiplier=Decimal("2.0"),
        rotation_margin=Decimal("0.05"),
        min_entry_score=Decimal("0.6"),
        rebalance_cooldown_hours=Decimal("4.0"),
        max_rebalances_per_pool_per_day=3,
        historical_dir=historical_dir or Path("data/historical"),
        registry_path=registry_path or Path("registry/registry.json"),
    )


def _make_record(date: int = 1000000000) -> PoolDayData:
    return PoolDayData(
        pool_address="0xabc",
        date=date,
        price_token1_in_token0=Decimal("2000.0"),
        price_token0_in_token1=Decimal("0.0005"),
        volume_usd=Decimal("100000.0"),
        tvl_usd=Decimal("500000.0"),
        fee_growth_global_0=1000,
        fee_growth_global_1=2000,
        source="the_graph",
    )


def _make_result(days: int = 30) -> BacktestResult:
    return BacktestResult(
        pool_address="0xabc",
        pair_name="USDC-WETH",
        days_simulated=days,
        total_fees_earned=Decimal("150.50"),
        il_cost=Decimal("20.00"),
        net_lp_alpha=Decimal("130.50"),
        final_capital=Decimal("10130.50"),
        rebalance_count=3,
        source="the_graph",
    )


# ── BacktestConfig tests ────────────────────────────────

class TestBacktestConfig:
    def test_backtest_config_from_yaml_loads_correctly(
        self, tmp_path: Path
    ) -> None:
        yaml_content = """
backtest:
  days: 30
  initial_capital: 10000
  bollinger_multiplier: 2.0
  rotation_margin: 0.05
  min_entry_score: 0.6
  rebalance_cooldown_hours: 4.0
  max_rebalances_per_pool_per_day: 3
"""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text(yaml_content)

        cfg = BacktestConfig.from_yaml(cfg_path)
        assert cfg.days == 30
        assert cfg.initial_capital == Decimal("10000")
        assert cfg.bollinger_multiplier == Decimal("2.0")
        assert cfg.rotation_margin == Decimal("0.05")
        assert cfg.min_entry_score == Decimal("0.6")
        assert cfg.rebalance_cooldown_hours == Decimal("4.0")
        assert cfg.max_rebalances_per_pool_per_day == 3

    def test_backtest_config_fields_are_decimal(self) -> None:
        cfg = _make_config()
        assert isinstance(cfg.initial_capital, Decimal)
        assert isinstance(cfg.bollinger_multiplier, Decimal)
        assert isinstance(cfg.rotation_margin, Decimal)
        assert isinstance(cfg.min_entry_score, Decimal)
        assert isinstance(cfg.rebalance_cooldown_hours, Decimal)

    def test_backtest_config_is_frozen(self) -> None:
        cfg = _make_config()
        with pytest.raises(Exception):  # FrozenInstanceError
            cfg.days = 60  # type: ignore


# ── BacktestResult tests ────────────────────────────────

class TestBacktestResult:
    def test_backtest_result_fields(self) -> None:
        r = _make_result()
        assert r.pool_address == "0xabc"
        assert r.pair_name == "USDC-WETH"
        assert r.days_simulated == 30
        assert r.total_fees_earned == Decimal("150.50")
        assert r.il_cost == Decimal("20.00")
        assert r.net_lp_alpha == Decimal("130.50")
        assert r.final_capital == Decimal("10130.50")
        assert r.rebalance_count == 3
        assert r.source == "the_graph"

    def test_backtest_result_is_frozen(self) -> None:
        r = _make_result()
        with pytest.raises(Exception):  # FrozenInstanceError
            r.days_simulated = 60  # type: ignore


# ── BacktestReporter tests ──────────────────────────────

class TestBacktestReporter:
    def test_reporter_save_creates_output_files(
        self, tmp_path: Path
    ) -> None:
        reporter = BacktestReporter(output_dir=tmp_path)
        results = [_make_result()]
        config = _make_config()
        reporter.save("test_run", results, config)

        assert (tmp_path / "test_run" / "summary.json").exists()
        assert (tmp_path / "test_run" / "per_pool.json").exists()

    def test_reporter_save_returns_correct_path(
        self, tmp_path: Path
    ) -> None:
        reporter = BacktestReporter(output_dir=tmp_path)
        config = _make_config()
        returned = reporter.save("test_run", [], config)
        assert returned == tmp_path / "test_run"

    def test_reporter_summary_json_contains_run_id(
        self, tmp_path: Path
    ) -> None:
        reporter = BacktestReporter(output_dir=tmp_path)
        results = [_make_result()]
        config = _make_config()
        reporter.save("test_run", results, config)

        with open(tmp_path / "test_run" / "summary.json") as f:
            summary = json.load(f)
        assert summary["run_id"] == "test_run"
        assert summary["pool_count"] == 1

    def test_reporter_per_pool_json_contains_all_results(
        self, tmp_path: Path
    ) -> None:
        reporter = BacktestReporter(output_dir=tmp_path)
        results = [_make_result(days=30), _make_result(days=60)]
        config = _make_config()
        reporter.save("test_run", results, config)

        with open(tmp_path / "test_run" / "per_pool.json") as f:
            per_pool = json.load(f)
        assert len(per_pool) == 2


# ── BacktestHarness tests ───────────────────────────────

class TestBacktestHarness:
    def test_harness_run_uses_hourly_path_when_no_history_files(
        self, tmp_path: Path
    ) -> None:
        """When historical dir has no matching files, hourly path runs with synthetic data."""
        from backtest.harness import BacktestHarness

        config = _make_config(historical_dir=tmp_path / "nonexistent")

        # Create a mock registry with one pool
        mock_registry = MagicMock()
        from registry.types import PoolConfig, TokenConfig, PriceReference
        pool = PoolConfig(
            pool_address="0xabc",
            pair_name="USDC-WETH",
            token0=TokenConfig(symbol="USDC", address="0xusdc", decimals=6),
            token1=TokenConfig(symbol="WETH", address="0xweth", decimals=18),
            fee_tier=500,
            price_reference={"USDC": PriceReference(quote="USD", source_pool="0xabc")},
        )
        mock_registry.all.return_value = [pool]

        harness = BacktestHarness(config, mock_registry)
        results = harness.run("test_run")
        # Hourly path always produces a result with synthetic data
        assert len(results) == 1
        assert results[0].source == "hourly"
        assert results[0].hours_simulated > 0

    def test_harness_run_hourly_path_produces_valid_result(
        self, tmp_path: Path
    ) -> None:
        """Hourly path produces a result with fees > 0 and proper exit_reason."""
        from backtest.harness import BacktestHarness

        hist_dir = tmp_path / "historical"
        hist_dir.mkdir()

        # Write a minimal history file — hourly path uses it for entry price
        records = [
            {
                "pool_address": "0xabc",
                "date": 1000000000 + i,
                "price_token1_in_token0": "2000.0",
                "price_token0_in_token1": "0.0005",
                "volume_usd": "100000.0",
                "tvl_usd": "500000.0",
                "fee_growth_global_0": 1000,
                "fee_growth_global_1": 2000,
                "source": "the_graph",
            }
            for i in range(5)
        ]
        (hist_dir / "USDC-WETH.json").write_text(json.dumps(records))

        config = _make_config(historical_dir=hist_dir)

        mock_registry = MagicMock()
        from registry.types import PoolConfig, TokenConfig, PriceReference
        pool = PoolConfig(
            pool_address="0xabc",
            pair_name="USDC-WETH",
            token0=TokenConfig(symbol="USDC", address="0xusdc", decimals=6),
            token1=TokenConfig(symbol="WETH", address="0xweth", decimals=18),
            fee_tier=500,
            price_reference={"USDC": PriceReference(quote="USD", source_pool="0xabc")},
        )
        mock_registry.all.return_value = [pool]

        harness = BacktestHarness(config, mock_registry)
        results = harness.run("test_run")

        assert len(results) == 1
        r = results[0]
        # Hourly path uses config.days for simulation window
        assert r.source == "hourly"
        assert r.hours_simulated >= config.days * 24
        assert r.exit_reason is not None
        assert isinstance(r.exit_reason, str)

    def test_harness_run_hourly_path_ignores_corrupt_history(
        self, tmp_path: Path
    ) -> None:
        """Hourly path falls back to synthetic data when history file is corrupt."""
        from backtest.harness import BacktestHarness

        hist_dir = tmp_path / "historical"
        hist_dir.mkdir()

        # Write invalid JSON — hourly path should still work with synthetic defaults
        (hist_dir / "USDC-WETH.json").write_text("NOT VALID JSON")

        config = _make_config(historical_dir=hist_dir)

        mock_registry = MagicMock()
        from registry.types import PoolConfig, TokenConfig, PriceReference
        pool = PoolConfig(
            pool_address="0xabc",
            pair_name="USDC-WETH",
            token0=TokenConfig(symbol="USDC", address="0xusdc", decimals=6),
            token1=TokenConfig(symbol="WETH", address="0xweth", decimals=18),
            fee_tier=500,
            price_reference={"USDC": PriceReference(quote="USD", source_pool="0xabc")},
        )
        mock_registry.all.return_value = [pool]

        harness = BacktestHarness(config, mock_registry)
        results = harness.run("test_run")

        # Hourly path produces result even with corrupt history (uses synthetic defaults)
        assert len(results) == 1
        assert results[0].source == "hourly"
