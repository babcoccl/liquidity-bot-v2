#!/usr/bin/env python3
"""
scripts/populate_registry.py

SPRINT 33: Populate registry/registry.json from memory/pool_reference.json.

Selection criteria:
  - TVL >= $100,000 (aggressive threshold)
  - Fee tier: 0.05% (bps=5), 0.3% (bps=30), 1% (bps=100) only
    (Excludes 0.01% stable-only tier and non-standard exotic tiers)
  - 24h volume >= $10,000 (p25 of active-volume pools at $100k TVL cohort)

Outputs:
  - registry/registry.json  (full rebuild, preserves correct schema)

Usage:
  python3 scripts/populate_registry.py [--dry-run] [--min-tvl N] [--min-vol N]

After running, re-run build_pool_reference.py to update in_registry counts.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
POOL_REFERENCE_PATH = REPO_ROOT / "memory" / "pool_reference.json"
REGISTRY_PATH = REPO_ROOT / "registry" / "registry.json"

# ---------------------------------------------------------------------------
# Selection criteria defaults (Sprint 33)
# ---------------------------------------------------------------------------
DEFAULT_MIN_TVL_USD: float = 100_000.0
DEFAULT_ALLOWED_FEE_BPS: frozenset[int] = frozenset({5, 30, 100})  # 0.05%, 0.3%, 1%
DEFAULT_MIN_VOLUME_24H_USD: float = 10_000.0

# Uniswap V3 fee tier units: fee_tier_bps -> raw fee_tier integer
FEE_BPS_TO_FEE_TIER: dict[int, int] = {
    5: 500,       # 0.05%
    30: 3_000,    # 0.3%
    100: 10_000,  # 1%
}

# Known token decimals. Tokens not listed here default to 18.
TOKEN_DECIMALS: dict[str, int] = {
    "WETH":   18, "cbBTC":  8,  "USDC":   6, "USDT":   6,
    "AERO":   18, "VIRTUAL":18, "FAI":    18, "WELL":   18,
    "fBOMB":  18, "VVV":    18, "DEGEN":  18, "BRETT":  18,
    "TOSHI":  18, "HIGHER": 18, "MOG":    18, "SKI":    18,
    "KAITO":  18, "PRIME":  18, "ZORA":   18, "KTA":    18,
    "DIEM":   18, "MET":    18, "SPX":    18, "EURC":    6,
    "cbETH":  18, "wstETH": 18, "rETH":   18,
}


def get_decimals(symbol: str) -> int:
    """Return token decimals from lookup table; default 18 for unknowns."""
    return TOKEN_DECIMALS.get(symbol, 18)


def build_registry_entry(p: dict, fee_bps: int) -> dict:
    """Convert a pool_reference pool dict into a registry entry."""
    t0 = p["token0_symbol"]
    t1 = p["token1_symbol"]
    fee_tier = FEE_BPS_TO_FEE_TIER[fee_bps]
    addr = p["pool_address"]
    return {
        "pool_address": addr,
        "pair_name": f"{t0}-{t1}-{fee_bps}",
        "token0": {
            "symbol": t0,
            "address": p["token0_address"],
            "decimals": get_decimals(t0),
        },
        "token1": {
            "symbol": t1,
            "address": p["token1_address"],
            "decimals": get_decimals(t1),
        },
        "fee_tier": fee_tier,
        "tick_lower": -887272,
        "tick_upper": 887272,
        "price_reference": {
            t0: {"quote": "USD", "source_pool": addr},
            t1: {"quote": "USD", "source_pool": addr},
        },
    }


def select_pools(
    pools: list[dict],
    min_tvl_usd: float,
    allowed_fee_bps: frozenset[int],
    min_volume_24h_usd: float,
) -> tuple[list[dict], dict[str, int]]:
    """Apply selection criteria; return (selected_pools, rejection_counts)."""
    rejected: dict[str, int] = {"status": 0, "tvl": 0, "fee_tier": 0, "volume": 0}
    selected: list[dict] = []

    for p in pools:
        if p.get("status") != "active":
            rejected["status"] += 1
            continue
        tvl = float(p.get("tvl_usd") or 0)
        if tvl < min_tvl_usd:
            rejected["tvl"] += 1
            continue
        bps = p.get("fee_tier_bps")
        if bps not in allowed_fee_bps:
            rejected["fee_tier"] += 1
            continue
        vol = float(p.get("volume_24h_usd") or 0)
        if vol < min_volume_24h_usd:
            rejected["volume"] += 1
            continue
        selected.append(p)

    return selected, rejected


def write_registry_atomic(registry: list[dict], output_path: Path) -> None:
    """Write registry JSON atomically (temp file + os.replace)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(registry, indent=2)
    # Validate before writing
    json.loads(content)
    fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, prefix=".registry_tmp_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written without modifying registry.json")
    parser.add_argument("--min-tvl", type=float, default=DEFAULT_MIN_TVL_USD,
                        help=f"Minimum TVL in USD (default: {DEFAULT_MIN_TVL_USD:,.0f})")
    parser.add_argument("--min-vol", type=float, default=DEFAULT_MIN_VOLUME_24H_USD,
                        help=f"Minimum 24h volume in USD (default: {DEFAULT_MIN_VOLUME_24H_USD:,.0f})")
    args = parser.parse_args()

    # --- Load pool reference ---
    if not POOL_REFERENCE_PATH.exists():
        print(f"ERROR: {POOL_REFERENCE_PATH} not found. Run scripts/build_pool_reference.py first.",
              file=sys.stderr)
        return 1

    print(f"Loading {POOL_REFERENCE_PATH} ...", flush=True)
    with open(POOL_REFERENCE_PATH, "r") as f:
        raw = json.load(f)
    all_pools = raw if isinstance(raw, list) else raw.get("pools", [])
    print(f"  Loaded {len(all_pools):,} total pool records.")

    # --- Apply selection ---
    selected, rejected = select_pools(
        all_pools,
        min_tvl_usd=args.min_tvl,
        allowed_fee_bps=DEFAULT_ALLOWED_FEE_BPS,
        min_volume_24h_usd=args.min_vol,
    )

    print(f"\nSelection criteria:")
    print(f"  TVL >= ${args.min_tvl:>12,.0f}")
    print(f"  Fee tiers: {sorted(DEFAULT_ALLOWED_FEE_BPS)} bps  (0.05%, 0.3%, 1%)")
    print(f"  24h vol >= ${args.min_vol:>11,.0f}")
    print(f"\nResults:")
    print(f"  SELECTED:              {len(selected):>5}")
    print(f"  Rejected (inactive):   {rejected['status']:>5}")
    print(f"  Rejected (TVL):        {rejected['tvl']:>5}")
    print(f"  Rejected (fee tier):   {rejected['fee_tier']:>5}")
    print(f"  Rejected (volume):     {rejected['volume']:>5}")
    print(f"  Total accounted for:   {len(selected) + sum(rejected.values()):>5}")

    if not selected:
        print("\nERROR: 0 pools selected — check criteria or pool_reference.json.", file=sys.stderr)
        return 1

    # --- Build registry entries ---
    registry = [build_registry_entry(p, p["fee_tier_bps"]) for p in selected]

    # --- Fee tier breakdown ---
    from collections import Counter
    fee_labels = Counter(p.get("fee_tier_label", "?") for p in selected)
    print(f"\nFee tier breakdown:")
    for label, count in sorted(fee_labels.items()):
        print(f"  {label}: {count} pools")

    # --- Top 10 preview ---
    print(f"\nTop 10 by TVL:")
    for i, p in enumerate(selected[:10]):
        print(
            f"  {i+1:2d}. {p['pair_name']:38s}"
            f"  TVL=${p['tvl_usd']:>12,.0f}"
            f"  vol24=${p['volume_24h_usd']:>12,.0f}"
            f"  fee={p['fee_tier_label']}"
        )

    # --- Write or dry-run ---
    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(registry)} entries to {REGISTRY_PATH}")
        print("[DRY RUN] No files modified.")
        return 0

    print(f"\nWriting {len(registry)} entries to {REGISTRY_PATH} ...", flush=True)
    write_registry_atomic(registry, REGISTRY_PATH)

    # --- Post-write validation ---
    with open(REGISTRY_PATH, "r") as f:
        verify = json.load(f)
    assert len(verify) == len(registry), "Post-write count mismatch!"
    print(f"  Validation: PASSED — {len(verify)} entries confirmed in registry.json")
    print(f"\nSPRINT 33 COMPLETE: {len(registry)} pools added to registry.")
    print("Next step: python3 scripts/build_pool_reference.py  (to update in_registry counts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
