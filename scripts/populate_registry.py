#!/usr/bin/env python3
"""
scripts/populate_registry.py

SPRINT 33: Populate registry/registry.json from memory/pool_reference.json.

Selection criteria (Sprint 33):
  - Minimum TVL: None — include all active CL pools
  - Fee tier filter: All — 100, 500, 3000, 10000 bps all included
  - Volume floor: None — TVL-only gating
  - gauge_alive: must be true (guaranteed by pool_reference.json source)
  - Pool type: CL only

Merge logic:
  - If a pool address already exists in registry, prefer the existing entry
    verbatim (preserves any manually set ticks or price_reference overrides).
  - Otherwise construct a fresh entry from pool_reference data.

Outputs:
  - registry/registry.json  (full rebuild, sorted by TVL descending)

Usage:
  python3 scripts/populate_registry.py [--dry-run]

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
# Fee tier mapping: fee_tier_bps (from pool_reference) -> raw fee_tier integer
# for registry schema. Aerodrome uses percentages; Uniswap V3 uses hundredths
# of a bps. Mapping: 5->500, 30->3000, 100->10000, etc.
# ---------------------------------------------------------------------------
FEE_BPS_TO_FEE_TIER: dict[int, int] = {
    1:   100,       # 0.01% -> 100
    5:   500,       # 0.05% -> 500
    10:  1000,      # 0.10% -> 1000
    30:  3_000,     # 0.30% -> 3000
    100: 10_000,    # 1.00% -> 10000
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


def fee_label_from_bps(fee_bps: int) -> str:
    """Convert fee_tier_bps to registry fee label (int(fee_tier / 100))."""
    fee_tier = FEE_BPS_TO_FEE_TIER.get(fee_bps, fee_bps * 100)
    return str(int(fee_tier / 100))


def build_registry_entry(p: dict) -> dict | None:
    """Convert a pool_reference pool dict into a registry entry.

    Returns None if required fields are missing.
    """
    addr = p.get("pool_address")
    t0_sym = p.get("token0_symbol")
    t1_sym = p.get("token1_symbol")
    t0_addr = p.get("token0_address")
    t1_addr = p.get("token1_address")
    fee_bps = p.get("fee_tier_bps")

    if not all([addr, t0_sym, t1_sym, t0_addr, t1_addr, fee_bps is not None]):
        return None

    fee_tier = FEE_BPS_TO_FEE_TIER.get(fee_bps, int(fee_bps * 100))
    fl = fee_label_from_bps(fee_bps)

    return {
        "pool_address": addr,
        "pair_name": f"{t0_sym}-{t1_sym}-{fl}",
        "token0": {
            "symbol": t0_sym,
            "address": t0_addr,
            "decimals": get_decimals(t0_sym),
        },
        "token1": {
            "symbol": t1_sym,
            "address": t1_addr,
            "decimals": get_decimals(t1_sym),
        },
        "fee_tier": fee_tier,
        "tick_lower": -887272,
        "tick_upper": 887272,
        "price_reference": {
            t0_sym: {"quote": "USD", "source_pool": addr},
            t1_sym: {"quote": "USD", "source_pool": addr},
        },
    }


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
    args = parser.parse_args()

    # --- Load pool reference ---
    if not POOL_REFERENCE_PATH.exists():
        print(
            "ERROR: pool_reference.json not found. Run build_pool_reference.py first.",
            file=sys.stderr,
        )
        return 1

    print(f"Loading {POOL_REFERENCE_PATH} ...", flush=True)
    with open(POOL_REFERENCE_PATH, "r") as f:
        raw = json.load(f)
    all_pools = raw if isinstance(raw, list) else raw.get("pools", [])
    print(f"  Loaded {len(all_pools):,} total pool records.")

    # --- Filter: active CL pools only ---
    active_pools = [p for p in all_pools if p.get("status") == "active"]
    print(f"  Active CL pools: {len(active_pools):,}")

    # --- Load existing registry for merge ---
    existing_by_addr: dict[str, dict] = {}
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, "r") as f:
                reg_raw = json.load(f)
            reg_list = reg_raw if isinstance(reg_raw, list) else reg_raw.get("pools", [])
            existing_by_addr = {
                entry.get("pool_address", "").lower(): entry
                for entry in reg_list
            }
            print(f"  Existing registry entries: {len(existing_by_addr):,}")
        except json.JSONDecodeError as e:
            print(f"WARN: registry.json invalid ({e}). Starting fresh.")

    # --- Build merged registry ---
    merged: list[dict] = []
    new_count = 0
    existing_count = 0
    skipped = 0

    for p in active_pools:
        addr_lower = p.get("pool_address", "").lower()
        if not addr_lower:
            skipped += 1
            continue

        entry = build_registry_entry(p)
        if entry is None:
            print(f"  WARN: skipping pool {addr_lower} — missing required fields")
            skipped += 1
            continue

        if addr_lower in existing_by_addr:
            # Prefer existing entry verbatim (preserves manual ticks/overrides)
            merged.append(existing_by_addr[addr_lower])
            existing_count += 1
        else:
            merged.append(entry)
            new_count += 1

    # --- Sort by TVL descending ---
    # Build a TVL lookup from active_pools for sorting
    tvl_lookup: dict[str, float] = {}
    for p in active_pools:
        addr_lower = p.get("pool_address", "").lower()
        tvl_lookup[addr_lower] = float(p.get("tvl_usd") or 0)

    merged.sort(key=lambda e: tvl_lookup.get(e.get("pool_address", "").lower(), 0), reverse=True)

    # --- Summary ---
    print(f"\n{'='*60}")
    print(f"POPULATE REGISTRY — SUMMARY")
    print(f"{'='*60}")
    print(f"Pools from pool_reference.json: {len(active_pools)}")
    print(f"Existing registry pools merged:  {existing_count}")
    print(f"New pools added:                 {new_count}")
    print(f"Total registry entries written:  {len(merged)}")
    if skipped:
        print(f"Skipped (missing fields):      {skipped}")

    # --- Fee tier breakdown ---
    from collections import Counter
    fee_counts = Counter()
    for e in merged:
        ft = e.get("fee_tier", "?")
        fee_counts[ft] += 1
    print(f"\nFee tier breakdown:")
    for ft, count in sorted(fee_counts.items(), key=lambda x: str(x[0])):
        print(f"  {ft}: {count} pools")

    # --- Top 10 preview ---
    print(f"\nTop 10 by TVL:")
    for i, e in enumerate(merged[:10]):
        tvl = tvl_lookup.get(e.get("pool_address", "").lower(), 0)
        print(f"  {i+1:3d}. {e['pair_name']:40s} TVL=${tvl:>12,.0f}")

    # --- Write or dry-run ---
    if args.dry_run:
        print(f"\n[DRY RUN] Would write {len(merged)} entries to {REGISTRY_PATH}")
        print("[DRY RUN] No files modified.")
        return 0

    if not merged:
        print("\nERROR: 0 pools selected — registry NOT overwritten.", file=sys.stderr)
        return 1

    print(f"\nWriting {len(merged)} entries to {REGISTRY_PATH} ...", flush=True)
    write_registry_atomic(merged, REGISTRY_PATH)

    # --- Post-write validation ---
    with open(REGISTRY_PATH, "r") as f:
        verify = json.load(f)
    assert len(verify) == len(merged), "Post-write count mismatch!"
    print(f"  Validation: PASSED — {len(verify)} entries confirmed in registry.json")

    # Print summary block (per .clinerules structured summary requirement)
    print()
    print("=== populate_registry.py SUMMARY ===")
    print(f"Pools from pool_reference.json: {len(active_pools)}")
    print(f"Existing registry pools merged:  {existing_count}")
    print(f"New pools added:                 {new_count}")
    print(f"Total registry entries written:  {len(merged)}")
    print("populate_registry.py COMPLETE.")

    return 0


if __name__ == "__main__":
    sys.exit(main())