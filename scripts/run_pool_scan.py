"""run_pool_scan.py — Rank all registered pools and write snapshot to results/.

Loads the full pool registry, all token price DataFrames, and all available
pool history files.  Assembles scorer-ready metrics for every pool via
build_all_pool_metrics, ranks them via rank_pools, classifies each pool's
risk tier, and writes the results atomically to
results/pool_scan_{UTC_ISO_timestamp}.json.

Usage:
    python scripts/run_pool_scan.py [--config PATH]

Exit codes:
    0 — success
    1 — unrecoverable error (registry validation, config parse, output write)

# AUDIT:status=complete
# AUDIT:sprint=37
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import yaml

from data.features.pool_feature_bridge import build_all_pool_metrics
from data.loader.pool_loader import load_pool_history
from data.loader.price_loader import load_all
from registry.registry import PoolRegistry
from strategy.scorer import classify_risk_tier, rank_pools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decimal serialization helper
# ---------------------------------------------------------------------------

_DECIMAL_KEYS = {
    "score",
    "net_lp_alpha_30d",
    "annualized_vol_30d",
    "fee_apr",
    "volume_tvl_ratio",
    "vol_24h",
    "momentum_24h",
    "momentum_168h",
    "vol_momentum_24h",
}


def _serialize_decimal(value: object) -> str:
    """Convert a Decimal value to its string representation for JSON output.

    Guards against Infinity / NaN by clamping to "0" and logging a WARNING.
    """
    if not isinstance(value, Decimal):
        return str(value)

    if value.is_infinite() or value.is_nan():
        logger.warning(
            "Encountered non-finite Decimal value %r — serializing as '0'", value,
        )
        return "0"

    return str(value)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run(config_path: str) -> int:
    """Execute the pool scan pipeline.  Returns exit code (0 or 1)."""

    # Capture timestamp at script start for deterministic output filename
    started_at = datetime.now(timezone.utc)
    timestamp_str = started_at.strftime("%Y%m%dT%H%M%SZ")
    generated_at = started_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── 1. Load & validate config ────────────────────────────────────────
    try:
        with open(config_path, "r") as fh:
            config = yaml.safe_load(fh)
    except Exception as exc:
        logger.error("Failed to load config at %s: %s", config_path, exc)
        print(f"ERROR: failed to load config: {exc}", file=sys.stderr)
        return 1

    try:
        prices_dir = str(config["backtest"]["prices_dir"])
        weights_raw = config["scoring"]["weights"]
        hard_gate = bool(config["scoring"]["hard_gate_net_lp_alpha"])
    except (KeyError, TypeError) as exc:
        logger.error("Config missing required key: %s", exc)
        print(
            f"ERROR: config malformed — missing key: {exc}", file=sys.stderr
        )
        return 1

    weights = {k: Decimal(str(v)) for k, v in weights_raw.items()}

    # ── 2. Load & validate registry ──────────────────────────────────────
    registry = PoolRegistry()
    registry.load()
    errors = registry.validate()
    if errors:
        print("ERROR: registry validation failed:", file=sys.stderr)
        for err in errors:
            logger.error("Registry validation error: %s", err)
            print(f"  - {err}", file=sys.stderr)
        return 1

    pool_configs = registry.all()
    logger.info("Loaded %d pools from registry", len(pool_configs))

    # ── 3. Load price DataFrames ─────────────────────────────────────────
    try:
        price_dfs = load_all(prices_dir, min_records=0)
    except Exception as exc:
        logger.error("Failed to load price data from %s: %s", prices_dir, exc)
        print(f"ERROR: failed to load prices: {exc}", file=sys.stderr)
        return 1

    logger.info(
        "Loaded price DataFrames for %d tokens", len(price_dfs)
    )

    # ── 4. Build pool_records_map ────────────────────────────────────────
    historical_dir = Path("data/historical")
    pool_records_map: dict[str, list] = {}

    for cfg in pool_configs:
        history_path = historical_dir / f"{cfg.pair_name}.json"
        try:
            records = load_pool_history(history_path)
            pool_records_map[cfg.pool_address.lower()] = records
        except FileNotFoundError:
            logger.debug(
                "No history file for %s at %s — including with empty records",
                cfg.pair_name,
                history_path,
            )
            pool_records_map[cfg.pool_address.lower()] = []

    # ── 5. Build metrics ─────────────────────────────────────────────────
    all_metrics = build_all_pool_metrics(
        pool_configs, price_dfs, pool_records_map, window_hours=720
    )
    logger.info("Built metrics for %d pools", len(all_metrics))

    # ── 6. Rank pools ────────────────────────────────────────────────────
    ranked = rank_pools(all_metrics, weights=weights, hard_gate=hard_gate)
    logger.info(
        "Ranked %d pools (hard_gate=%s)", len(ranked), hard_gate
    )

    # ── 7. Assemble output ───────────────────────────────────────────────
    metrics_by_pool_id = {m["pool_id"]: m for m in all_metrics}

    pools_out: list[dict] = []
    for rank_idx, (pool_id, score) in enumerate(ranked, start=1):
        m = metrics_by_pool_id.get(pool_id, {})

        risk_tier = classify_risk_tier(
            annualized_vol=m.get("annualized_vol_30d", Decimal("0")),
            fee_apr=m.get("fee_apr", Decimal("0")),
        )

        entry: dict = {
            "rank": rank_idx,
            "pool_id": pool_id,
            "pair_name": m.get("pair_name", ""),
            "score": _serialize_decimal(score),
            "risk_tier": risk_tier,
            "net_lp_alpha_30d": _serialize_decimal(
                m.get("net_lp_alpha_30d", Decimal("0"))
            ),
            "annualized_vol_30d": _serialize_decimal(
                m.get("annualized_vol_30d", Decimal("0"))
            ),
            "fee_apr": _serialize_decimal(m.get("fee_apr", Decimal("0"))),
            "volume_tvl_ratio": _serialize_decimal(
                m.get("volume_tvl_ratio", Decimal("0"))
            ),
            "vol_24h": _serialize_decimal(m.get("vol_24h", Decimal("0"))),
            "momentum_24h": _serialize_decimal(
                m.get("momentum_24h", Decimal("0"))
            ),
            "momentum_168h": _serialize_decimal(
                m.get("momentum_168h", Decimal("0"))
            ),
            "vol_momentum_24h": _serialize_decimal(
                m.get("vol_momentum_24h", Decimal("0"))
            ),
            "price_features_ok": bool(m.get("price_features_ok", False)),
            "pool_records_ok": bool(m.get("pool_records_ok", False)),
        }
        pools_out.append(entry)

    output = {
        "generated_at": generated_at,
        "pool_count": len(pool_configs),
        "ranked_count": len(ranked),
        "config_path": config_path,
        "pools": pools_out,
    }

    # ── 8. Atomic write ──────────────────────────────────────────────────
    results_dir = Path("results")
    output_filename = f"pool_scan_{timestamp_str}.json"
    output_path = results_dir / output_filename
    tmp_path = results_dir / (output_filename + ".tmp")

    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w") as fh:
            json.dump(output, fh, indent=2)
        os.replace(str(tmp_path), str(output_path))
    except Exception as exc:
        logger.error("Failed to write output to %s: %s", output_path, exc)
        print(f"ERROR: failed to write output: {exc}", file=sys.stderr)
        # Clean up tmp on failure
        try:
            if tmp_path.exists():
                os.unlink(str(tmp_path))
        except OSError:
            pass
        return 1

    print(
        f"Pool scan complete: {len(ranked)} pools ranked, "
        f"output → {output_path}"
    )
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank all registered liquidity pools and write a snapshot."
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to YAML config file (default: config/default.yaml)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    exit_code = run(args.config)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()