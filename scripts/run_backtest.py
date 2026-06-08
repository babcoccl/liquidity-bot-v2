"""ONE-SHOT BACKTEST RUNNER. REAL DATA. WRITE RESULTS TO results/runs/.

# AUDIT:status=complete
# AUDIT:sprint=22
# AUDIT:issue=none
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from pathlib import Path

from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from registry.registry import PoolRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
REGISTRY_PATH = Path("registry/registry.json")
HISTORICAL_DIR = Path("data/historical")
PRICES_DIR = Path("data/prices")
RESULTS_DIR = Path("results")


def build_config() -> BacktestConfig:
    """BUILD REAL DATA BACKTEST CONFIG. ALL PATHS POINT AT data/.

    INITIAL_CAPITAL 10000. DAYS 30. ENTRY SCORE LOW — LET ALL POOLS ENTER.
    MAX_IL_PCT WIDE — DO NOT FILTER ON FIRST REAL RUN. OBSERVE RESULTS FIRST.
    """
    return BacktestConfig(
        days=30,
        initial_capital=Decimal("10000"),
        # LOW ENTRY SCORE SO ALL POOLS ENTER FOR FIRST VALIDATION RUN
        min_entry_score=Decimal("0.05"),
        # WIDE IL EXIT — RARELY TRIGGERS ON FIRST RUN. OBSERVE FIRST.
        max_il_pct=Decimal("-0.50"),
        # LOW THRESHOLDS SO REAL DATA PASSES FILTERS
        min_tvl_usd=Decimal("100000"),
        min_volume_usd=Decimal("10000"),
        # HOLD UP TO 720 HOURS (30 DAYS). WINDOW 336 HOURS (14 DAYS).
        max_hold_hours=720,
        metrics_window_hours=336,
        # BOLLINGER + ROTATION PARAMS
        bollinger_multiplier=Decimal("2"),
        rotation_margin=Decimal("0.05"),
        # REBALANCE LIMITS
        rebalance_cooldown_hours=Decimal("4"),
        max_rebalances_per_pool_per_day=6,
        # PATHS — ALL POINT AT REAL DATA DIRS
        historical_dir=HISTORICAL_DIR,
        prices_dir=PRICES_DIR,
        hourly_dir=HISTORICAL_DIR,
        registry_path=REGISTRY_PATH,
    )


def make_run_id() -> str:
    """MAKE RUN ID. FORMAT: real_YYYY-MM-DD."""
    return f"real_{datetime.date.today().isoformat()}"


def main() -> None:
    """RUN BACKTEST ON REAL DATA. PRINT SUMMARY PATH WHEN DONE."""
    logging.basicConfig(level=logging.INFO)

    config = build_config()
    logger.info("Config built: days=%d, capital=%s", config.days, config.initial_capital)

    registry = PoolRegistry(path=REGISTRY_PATH)
    registry.load()
    logger.info("Registry loaded %d pool(s)", len(registry.all()))

    run_id = make_run_id()
    logger.info("Run ID: %s", run_id)

    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id=run_id)

    summary_path = RESULTS_DIR / "runs" / run_id / "summary.json"

    pools_simulated = sum(1 for r in results if r.hours_simulated > 0)
    pools_skipped = sum(1 for r in results if r.hours_simulated == 0)

    print(f"DONE. SUMMARY: {summary_path}")
    print(f"POOLS SIMULATED: {pools_simulated}")
    print(f"POOLS SKIPPED: {pools_skipped}")


if __name__ == "__main__":
    main()