"""
run_backtest.py — Backtest execution script (Sprint 38)

Loads BacktestConfig from YAML, validates PoolRegistry, runs the backtest
via BacktestHarness, and emits results via BacktestReporter.

Usage:
    python scripts/run_backtest.py [--config PATH] [--run-id STRING] [--debug]

Notes:
    --run-id containing path separators (e.g., ../../etc) is not sanitized
    in this sprint — document as known constraint.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path

# Local imports
from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from backtest.reporter import BacktestReporter
from registry.registry import PoolRegistry

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the full backtest harness and report results."
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to YAML config file (default: config/default.yaml).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Run identifier for output directory. "
            "Default: UTC datetime formatted as backtest_YYYYMMDDTHHMMSSZ."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    args = parser.parse_args()

    # ── Logging setup ────────────────────────────────────────────
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)-8s %(name)s — %(message)s")
    logger.debug("DEBUG logging enabled")

    # Capture script-start time for default run_id
    run_id: str = (
        args.run_id
        if args.run_id is not None
        else datetime.datetime.now(datetime.timezone.utc).strftime("backtest_%Y%m%dT%H%M%SZ")
    )

    config_path = Path(args.config)

    # ── Load config ──────────────────────────────────────────────
    try:
        config = BacktestConfig.from_yaml(config_path)
    except Exception:
        msg = f"Failed to load config from {config_path}: {sys.exc_info()[1]}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    logger.info("Config loaded: %s pools registry at %s", len(config.registry_path.name), config.registry_path)

    # ── Load and validate registry ───────────────────────────────
    try:
        registry = PoolRegistry(config.registry_path)
        registry.load()
    except Exception:
        msg = f"Failed to load registry from {config.registry_path}: {sys.exc_info()[1]}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    errors = registry.validate()
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        logger.error("Registry validation failed with %d error(s)", len(errors))
        sys.exit(1)

    all_pools = registry.all()
    logger.info("Registry OK: %d pools", len(all_pools))

    # ── Run backtest harness ─────────────────────────────────────
    try:
        harness = BacktestHarness(config=config, registry=registry)
        results = harness.run(run_id)
    except Exception:
        msg = f"BacktestHarness.run() raised an unexpected exception: {sys.exc_info()[1]}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    simulated_count = len(results)
    logger.info("Harness complete: %d pools evaluated, %d simulated", len(all_pools), simulated_count)

    # ── Reporting ────────────────────────────────────────────────
    reporter = BacktestReporter(output_dir=Path("results"))

    # Print table first (spec requirement: print_summary before save so
    # table is visible even if save fails)
    try:
        reporter.print_summary(run_id, results)
    except Exception:
        msg = f"reporter.print_summary() raised: {sys.exc_info()[1]}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        # Still attempt save after logging the error

    try:
        reporter.save(run_id, results, config)
    except Exception:
        msg = f"reporter.save() failed (results not persisted): {sys.exc_info()[1]}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)

    # ── Completion summary line ──────────────────────────────────
    print(
        f"Backtest complete: {len(all_pools)} pools evaluated, "
        f"{simulated_count} simulated — results → results/runs/{run_id}/"
    )


if __name__ == "__main__":
    main()