"""
CLI entrypoint: run a backtest over all pools in the registry.
LEGACY RUNNER — Sprint 6. Use scripts/run_backtest.py for real data runs.

Usage:
    python scripts/run_backtest_legacy.py [--run-id <id>] [--days <n>] [--config <path>]

Loads config from config/default.yaml.
Loads registry from registry/registry.json.
Expects historical data in data/historical/<pair_name>.json.
Saves results to results/<run_id>/.

# AUDIT:status=complete
# AUDIT:sprint=6
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dataclasses import replace

from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from registry.registry import PoolRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a backtest over all pools in the registry.")
    parser.add_argument(
        "--run-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Run identifier (default: ISO timestamp YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override number of days to simulate (default: from config)",
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to config file (default: config/default.yaml)",
    )
    args = parser.parse_args()

    # Load config
    config = BacktestConfig.from_yaml(Path(args.config))

    # Override days if provided
    if args.days is not None:
        config = replace(config, days=args.days)

    # Load and validate registry
    registry = PoolRegistry(config.registry_path)
    registry.load()
    errors = registry.validate()
    for err in errors:
        logger.warning("Registry validation: %s", err)

    # Run backtest
    harness = BacktestHarness(config, registry)
    results = harness.run(args.run_id)

    logger.info("Backtest complete. %d pool(s) simulated.", len(results))


if __name__ == "__main__":
    main()
