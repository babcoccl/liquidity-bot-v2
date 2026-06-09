"""ONE-SHOT BACKTEST RUNNER. REAL DATA. WRITE RESULTS TO results/runs/.

# AUDIT:status=complete
# AUDIT:sprint=25
# AUDIT:issue=none
"""

from __future__ import annotations

import argparse
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


def build_config(days: int = 30) -> BacktestConfig:
    """BUILD REAL DATA BACKTEST CONFIG. ALL PATHS POINT AT data/.

    INITIAL_CAPITAL 10000. DAYS CONFIGURABLE VIA --days FLAG.
    MAX_HOLD_HOURS = DAYS * 24 SO SIMULATION RUNS FULL WINDOW.
    """
    return BacktestConfig(
        days=days,
        initial_capital=Decimal("10000"),
        min_entry_score=Decimal("0.05"),
        max_il_pct=Decimal("-0.50"),
        min_tvl_usd=Decimal("100000"),
        min_volume_usd=Decimal("10000"),
        max_hold_hours=days * 24,
        metrics_window_hours=336,
        bollinger_multiplier=Decimal("2"),
        rotation_margin=Decimal("0.05"),
        rebalance_cooldown_hours=Decimal("4"),
        max_rebalances_per_pool_per_day=6,
        historical_dir=HISTORICAL_DIR,
        prices_dir=PRICES_DIR,
        hourly_dir=HISTORICAL_DIR,
        registry_path=REGISTRY_PATH,
    )


def parse_args() -> argparse.Namespace:
    """PARSE CLI ARGS. --days N."""
    parser = argparse.ArgumentParser(description="Run backtest on real data")
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days to simulate (default: 30). "
             "Must match or be less than days fetched by fetch.py.",
    )
    return parser.parse_args()


def make_run_id(days: int) -> str:
    """MAKE RUN ID. FORMAT: real_YYYY-MM-DD_Nd."""
    date = datetime.date.today().isoformat()
    return f"real_{date}_{days}d"


def main() -> None:
    """RUN BACKTEST ON REAL DATA. PRINT SUMMARY PATH WHEN DONE."""
    logging.basicConfig(level=logging.INFO)

    args = parse_args()
    days = args.days

    config = build_config(days=days)
    logger.info("Config built: days=%d, capital=%s", config.days, config.initial_capital)

    registry = PoolRegistry(path=REGISTRY_PATH)
    registry.load()
    logger.info("Registry loaded %d pool(s)", len(registry.all()))

    run_id = make_run_id(days=days)
    logger.info("Run ID: %s", run_id)

    harness = BacktestHarness(config=config, registry=registry)
    results = harness.run(run_id=run_id)

    summary_path = RESULTS_DIR / "runs" / run_id / "summary.json"

    pools_simulated = sum(1 for r in results if r.hours_simulated > 0)
    pools_skipped = sum(1 for r in results if r.hours_simulated == 0)

    print("=== BACKTEST SUMMARY ===")
    for r in results:
        cap = getattr(r, "final_capital", None)
        hrs = getattr(r, "hours_simulated", 0)
        pool = getattr(r, "pool_address", "unknown")[:10]
        pair = getattr(r, "pair_name", pool)
        if hrs == 0:
            print(f"  {pair:<14} SKIPPED")
        else:
            cap_str = str(cap) if cap is not None else "N/A"
            print(f"  {pair:<14} hrs={hrs:>4}  final_capital={cap_str}")
    print(f"POOLS SIMULATED: {pools_simulated}")
    print(f"POOLS SKIPPED:   {pools_skipped}")
    print(f"SUMMARY JSON:    {summary_path}")
    print("BACKTEST COMPLETE.")


if __name__ == "__main__":
    main()