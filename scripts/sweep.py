"""
CLI entrypoint: run a parameter sweep over exit-policy parameters.

Usage:
    python scripts/sweep.py [--sweep-id <id>] [--config <path>]
                            [--il <v1,v2,...>] [--hold <v1,v2,...>]
                            [--tvl <v1,v2,...>] [--vol <v1,v2,...>]

Defaults (when flag omitted):
    --il    "-0.03,-0.05,-0.10"
    --hold  "168,336,720"
    --tvl   "100000,500000"
    --vol   "10000,50000"

# AUDIT:status=complete
# AUDIT:sprint=15
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from backtest.config import BacktestConfig
from backtest.sweep import SweepConfig, SweepRunner
from registry.registry import PoolRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a parameter sweep over exit-policy parameters.")
    parser.add_argument(
        "--sweep-id",
        default=datetime.now().strftime("%Y%m%d_%H%M%S"),
        help="Sweep identifier (default: ISO timestamp YYYYMMDD_HHMMSS)",
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to config file (default: config/default.yaml)",
    )
    parser.add_argument(
        "--il",
        default="-0.03,-0.05,-0.10",
        help="Comma-separated max_il_pct values (default: -0.03,-0.05,-0.10)",
    )
    parser.add_argument(
        "--hold",
        default="168,336,720",
        help="Comma-separated max_hold_hours values (default: 168,336,720)",
    )
    parser.add_argument(
        "--tvl",
        default="100000,500000",
        help="Comma-separated min_tvl_usd values (default: 100000,500000)",
    )
    parser.add_argument(
        "--vol",
        default="10000,50000",
        help="Comma-separated min_volume_usd values (default: 10000,50000)",
    )
    args = parser.parse_args()

    # Parse comma-separated values
    il_values = [Decimal(v) for v in args.il.split(",")]
    hold_values = [int(v) for v in args.hold.split(",")]
    tvl_values = [Decimal(v) for v in args.tvl.split(",")]
    vol_values = [Decimal(v) for v in args.vol.split(",")]

    # Load config
    config = BacktestConfig.from_yaml(Path(args.config))

    # Load and validate registry
    registry = PoolRegistry(config.registry_path)
    registry.load()
    errors = registry.validate()
    for err in errors:
        logger.warning("Registry validation: %s", err)

    # Build sweep config
    sweep_config = SweepConfig(
        max_il_pct_values=il_values,
        max_hold_hours_values=hold_values,
        min_tvl_usd_values=tvl_values,
        min_volume_usd_values=vol_values,
        base_config=config,
    )

    # Run sweep
    runner = SweepRunner(sweep_config=sweep_config, registry=registry)
    results = runner.run(args.sweep_id)
    output_path = runner.save(args.sweep_id, results)

    print(f"Sweep complete. {len(results)} combinations. Results at: {output_path}")


if __name__ == "__main__":
    main()