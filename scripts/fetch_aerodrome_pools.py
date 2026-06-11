#!/usr/bin/env python3
"""
Sprint 33-Pre: Fetch Aerodrome Slipstream CL pool registry via Sugar SDK.

Reads directly from Aerodrome's on-chain Sugar helper contract on Base.
No scraping, no API keys required for public RPC.
Outputs memory/pool_reference_raw.json

Usage:
    pip install git+https://github.com/velodrome-finance/sugar-sdk
    python3 scripts/fetch_aerodrome_pools.py

Optional env vars:
    SUGAR_RPC_URI_8453  — override default Base RPC (recommended for production)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from sugar.chains import BaseChain
except ImportError:
    print("FAILED: sugar-sdk not installed.")
    print("Run: pip install git+https://github.com/velodrome-finance/sugar-sdk")
    sys.exit(1)

RAW_OUTPUT = Path("memory/pool_reference_raw.json")
SOURCE_URL = "https://aerodrome.finance/liquidity?filters=listed%2Cconcentrated&sort=tvl%3Adesc"
MIN_TVL_USD = 100_000  # Exclude pools below this TVL threshold

# Concentrated LP pool type identifiers used by Sugar SDK
# type > 0 = Slipstream CL (value = tick_spacing, e.g., 1, 5, 30)
# type == -1 = volatile vAMM
# type == 0 = stable sAMM


def is_cl_pool(pool) -> bool:
    """Return True if pool is a concentrated liquidity (Slipstream) pool.

    Slipstream CL pools have type > 0 (the value equals tick_spacing).
    type == -1 is volatile vAMM, type == 0 is stable sAMM — both excluded.
    """
    pool_type = getattr(pool, "type", None)
    return pool_type is not None and pool_type > 0


def is_migrating(pool) -> bool:
    """Return True if pool is tagged as migrating."""
    # Sugar SDK exposes gauge_alive as a boolean directly on the pool object.
    # Migrating pools have gauge_alive == False and are superseded by newer pools.
    alive = getattr(pool, "gauge_alive", None)
    if alive is not None and not alive:
        return True
    symbol = getattr(pool, "symbol", "") or ""
    return "migrat" in symbol.lower()


def get_gauge_address(pool) -> str:
    """Extract gauge contract address from pool object.

    Sugar SDK returns `gauge` as a string address (not an object).
    """
    gauge = getattr(pool, "gauge", None)
    if gauge is None or gauge == "":
        return "NOT_FOUND"
    # gauge is already a string address like '0x50f0249B824033Cf0AF0C8b9fe1c67c2842A34d5'
    return str(gauge).lower()


def pool_to_dict(pool, status: str) -> dict:
    """Convert a Sugar SDK pool object to a serializable dict."""
    token0 = getattr(pool, "token0", None)
    token1 = getattr(pool, "token1", None)

    t0_symbol = getattr(token0, "symbol", "") if token0 else ""
    t1_symbol = getattr(token1, "symbol", "") if token1 else ""
    t0_address = str(getattr(token0, "token_address", "")).lower() if token0 else ""
    t1_address = str(getattr(token1, "token_address", "")).lower() if token1 else ""

    pool_address = str(getattr(pool, "lp", "")).lower()
    gauge_address = get_gauge_address(pool)

    # Fee tier: Sugar SDK returns pool_fee_percentage (e.g., 0.3 means 0.3%)
    # and pool_fee (raw integer, e.g., 30). Use pool_fee_percentage directly.
    fee_tier_pct = float(getattr(pool, "pool_fee_percentage", 0) or 0)
    fee_tier_bps = int(round(fee_tier_pct * 100)) if fee_tier_pct > 0 else 0
    # Map to standard label
    fee_label_map = {0.01: "0.01%", 0.05: "0.05%", 0.3: "0.3%", 1.0: "1%"}
    fee_tier_label = fee_label_map.get(fee_tier_pct, f"{fee_tier_pct:.4f}%") if fee_tier_pct > 0 else "unknown"

    tvl = float(getattr(pool, "tvl", 0) or 0)
    volume = float(getattr(pool, "volume", 0) or 0)
    total_fees = float(getattr(pool, "total_fees", 0) or 0)
    apr = float(getattr(pool, "apr", 0) or 0)

    implied_daily_fees = round(volume * (fee_tier_bps / 10_000_000), 2) if fee_tier_bps else round(total_fees, 2)
    implied_daily_fee_apr = round((implied_daily_fees / tvl * 365 * 100) if tvl > 0 else 0.0, 2)

    return {
        "pair_name": f"{t0_symbol}/{t1_symbol}",
        "symbol": getattr(pool, "symbol", ""),
        "pool_address": pool_address,
        "gauge_address": gauge_address,
        "token0_symbol": t0_symbol,
        "token1_symbol": t1_symbol,
        "token0_address": t0_address,
        "token1_address": t1_address,
        "pool_fee_raw": getattr(pool, "pool_fee", None),
        "fee_tier_bps": fee_tier_bps,
        "fee_tier_label": fee_tier_label,
        "tvl_usd": round(tvl, 2),
        "volume_24h_usd": round(volume, 2),
        "total_fees_usd": round(total_fees, 6),
        "apr_pct": round(apr, 4),
        "implied_daily_fees_usd": implied_daily_fees,
        "implied_daily_fee_apr_pct": implied_daily_fee_apr,
        "status": status,
        "in_registry": False,  # populated by build_pool_reference.py
        # Placeholders for cross-validation — filled by GT/DeFiLlama passes
        "gt_tvl_usd": None,
        "gt_volume_24h_usd": None,
        "defillama_uuid": "",
        "defillama_tvl_usd": None,
        "defillama_project_tag": "",
        "tvl_source_decision": "Aerodrome (Sugar SDK)",
        "notes": ""
    }


def main():
    print("=" * 60)
    print("AERODROME POOL FETCHER — Sugar SDK — Sprint 33-Pre")
    print("=" * 60)
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")

    rpc = os.environ.get("SUGAR_RPC_URI_8453", "(default public RPC)")
    print(f"RPC: {rpc}")
    print()

    print("Connecting to Base via Sugar SDK...")
    with BaseChain() as chain:
        print("Fetching all pools from on-chain Sugar contract...")
        all_pools = chain.get_pools()
        print(f"Total pools returned by Sugar: {len(all_pools)}")

    # Partition: CL active, CL migrating, non-CL (excluded)
    cl_active = []
    cl_migrating = []
    non_cl = []

    for pool in all_pools:
        if not is_cl_pool(pool):
            non_cl.append(pool)
            continue
        if is_migrating(pool):
            cl_migrating.append(pool)
        else:
            cl_active.append(pool)

    # Filter by minimum TVL threshold
    before_tvl_filter = len(cl_active)
    cl_active = [p for p in cl_active if (float(getattr(p, "tvl", 0) or 0)) >= MIN_TVL_USD]
    filtered_by_tvl = before_tvl_filter - len(cl_active)

    print(f"Concentrated (active):    {len(cl_active)}")
    print(f"Concentrated (migrating): {len(cl_migrating)}")
    print(f"Basic/other (excluded):   {len(non_cl)}")
    print(f"Filtered by TVL < ${MIN_TVL_USD:,}:  {filtered_by_tvl}")
    print()

    # Serialize
    active_dicts = [pool_to_dict(p, "active") for p in cl_active]
    migrating_dicts = [pool_to_dict(p, "migrating") for p in cl_migrating]

    # Sort active by TVL descending
    active_dicts.sort(key=lambda p: p["tvl_usd"], reverse=True)
    migrating_dicts.sort(key=lambda p: p["tvl_usd"], reverse=True)

    all_output = active_dicts + migrating_dicts

    print("TOP 10 ACTIVE CL POOLS BY TVL:")
    for i, p in enumerate(active_dicts[:10], 1):
        print(f"  {i:2}. {p['pair_name']:25} TVL=${p['tvl_usd']:>12,.2f}  "
              f"APR={p['apr_pct']:>7.2f}%  addr={p['pool_address']}")

    # Write raw output atomically
    RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "schema_version": 1,
        "scraped_at": datetime.now(timezone.utc).isoformat() + "Z",
        "source": "Aerodrome Sugar SDK (on-chain)",
        "source_url": SOURCE_URL,
        "chain": "Base",
        "chain_id": 8453,
        "protocol": "Aerodrome Slipstream",
        "total_cl_active": len(active_dicts),
        "total_cl_migrating": len(migrating_dicts),
        "total_basic_excluded": len(non_cl),
        "pools_raw": all_output,
    }

    tmp = RAW_OUTPUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(output, indent=2))
    tmp.replace(RAW_OUTPUT)

    print()
    print(f"WROTE {len(all_output)} pools to {RAW_OUTPUT}")
    print("FETCH COMPLETE.")


if __name__ == "__main__":
    main()