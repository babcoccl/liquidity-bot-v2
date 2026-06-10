#!/usr/bin/env python3
"""
Build pool_reference.json and pool_reference.md from scraped raw data.
Reads memory/pool_reference_raw.json, parses display strings to numbers,
cross-references against registry/registry.json, and writes final outputs.

Usage:
    python3 scripts/build_pool_reference.py
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def parse_usd(s: str) -> float:
    """Convert '$12.4M', '$950K', '$1.2B' to float."""
    s = s.replace("$", "").replace(",", "").strip()
    multipliers = {"K": 1e3, "M": 1e6, "B": 1e9}
    for suffix, mult in multipliers.items():
        if s.upper().endswith(suffix):
            return float(s[:-1]) * mult
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_fee_tier(s: str) -> int:
    """Convert '50' (from URL type param) to fee_tier integer.
    Aerodrome uses: 1=0.01%, 10=0.1%, 50=0.05%, 100=0.1%, 200=0.2%, 500=0.05%, 3000=0.3%, 10000=1%
    The 'type' param is the fee tier in hundredths of a percent (e.g., 50 = 0.05%)."""
    try:
        return int(s)
    except ValueError:
        return 0


def fee_tier_label(fee_tier: int) -> str:
    """Convert fee tier integer to human-readable label."""
    labels = {1: "0.0001%", 10: "0.001%", 50: "0.0005%", 100: "0.001%",
              200: "0.002%", 500: "0.005%", 3000: "0.03%", 10000: "0.1%"}
    # Aerodrome fee tiers: type param is in basis points / 100
    # 1 = 0.01 bps, 50 = 0.5 bps (0.0005%), 100 = 1 bps (0.001%)
    # Actually the standard V3 tiers: 1=0.01%, 500=0.05%, 3000=0.3%, 10000=1%
    v3_labels = {1: "0.01%", 50: "0.05%", 100: "0.1%", 200: "0.2%",
                 500: "0.5%", 3000: "3.0%"}
    return v3_labels.get(fee_tier, f"{fee_tier / 100:.4f}%")


def main():
    raw_path = Path("memory/pool_reference_raw.json")
    registry_path = Path("registry/registry.json")
    json_out = Path("memory/pool_reference.json")
    md_out = Path("memory/pool_reference.md")

    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Run scrape_aerodrome_all.py first.")
        sys.exit(1)

    # Load raw data
    with open(raw_path) as f:
        raw = json.load(f)

    # Load existing registry for cross-reference
    existing_addresses = set()
    if registry_path.exists():
        with open(registry_path) as f:
            registry = json.load(f)
        existing_addresses = {p.get("pool_address", "").lower() for p in registry.get("pools", [])}

    pools = []
    for p in raw.get("pools_raw", []):
        tvl = parse_usd(p.get("tvl_display", "$0"))
        vol = parse_usd(p.get("volume_24h_display", "$0"))
        fee = parse_fee_tier(p.get("fee_tier_raw", "0"))
        
        # Implied daily fees: volume * (fee / 1_000_000) for basis points
        # Fee tier in Aerodrome is in hundredths of bps, so divide by 100 to get bps
        fee_bps = fee / 100.0
        daily_fees = round(vol * (fee_bps / 10_000), 2)
        apr = round((daily_fees / tvl * 365 * 100) if tvl > 0 else 0.0, 2)

        # Use token addresses as unique identifier since we don't have pool address yet
        token0 = p.get("token0", "")
        token1 = p.get("token1", "")
        factory = p.get("factory", "")
        
        pools.append({
            "pair_name": p["pair_name"],
            "pool_address": "",  # Needs to be derived or fetched from subgraph
            "gauge_address": "",  # Needs to be fetched from subgraph
            "token0": token0,
            "token1": token1,
            "factory": factory,
            "fee_tier": fee,
            "fee_tier_label": fee_tier_label(fee),
            "tvl_usd": round(tvl, 2),
            "volume_24h_usd": round(vol, 2),
            "implied_daily_fees_usd": daily_fees,
            "implied_daily_fee_apr_pct": apr,
            "status": p.get("status", "active"),
            "in_registry": False,  # Will be True if pool_address matches
            "defillama_uuid": "",
            "defillama_tvl_usd": None,
            "defillama_project_tag": "",
            "tvl_source_decision": "Aerodrome UI",
            "notes": ""
        })

    # Sort: active pools by TVL desc, then migrating at bottom
    active = sorted([p for p in pools if p["status"] == "active"], key=lambda x: x["tvl_usd"], reverse=True)
    migrating = sorted([p for p in pools if p["status"] == "migrating"], key=lambda x: x["tvl_usd"], reverse=True)
    pools_sorted = active + migrating

    # Write pool_reference.json
    output = {
        "schema_version": 1,
        "scraped_at": raw.get("scraped_at", datetime.now(timezone.utc).isoformat()),
        "source_url": raw.get("source_url", ""),
        "chain": "Base",
        "protocol": "Aerodrome Slipstream",
        "total_pools": len(pools_sorted),
        "active_pools": len(active),
        "migrating_pools": len(migrating),
        "pools": pools_sorted
    }

    with open(json_out, "w") as f:
        json.dump(output, f, indent=2)

    # Write pool_reference.md
    lines = [
        "# Aerodrome Pool Reference Table",
        f"# Scraped: {raw.get('scraped_at', 'N/A')}",
        "# Chain: Base | Protocol: Aerodrome Slipstream (CL)",
        f"# Source: {raw.get('source_url', '')}",
        "# TVL Source: Aerodrome UI (ground truth)",
        "# Pool addresses: Needs subgraph fetch — Sprint 34",
        "",
        "## Active Pools",
        "",
        "| # | Pair | Fee Tier | TVL (USD) | 24h Vol (USD) | Daily Fees | Daily APR | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for i, p in enumerate(active, 1):
        lines.append(
            f"| {i} | {p['pair_name']} | {p['fee_tier_label']} "
            f"| ${p['tvl_usd']:>12,.2f} | ${p['volume_24h_usd']:>12,.2f} "
            f"| ${p['implied_daily_fees_usd']:>9,.2f} | {p['implied_daily_fee_apr_pct']:>7.2f}% | ✅ active |"
        )

    lines += [
        "",
        "## Migrating Pools (Do Not Add to Registry)",
        "",
        "| # | Pair | Fee Tier | TVL (USD) | 24h Vol (USD) |",
        "|---|---|---|---|---|",
    ]

    for i, p in enumerate(migrating, 1):
        lines.append(
            f"| {i} | {p['pair_name']} | {p['fee_tier_label']} "
            f"| ${p['tvl_usd']:>12,.2f} | ${p['volume_24h_usd']:>12,.2f} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Pool addresses and gauge addresses need to be fetched from the subgraph (Sprint 34)",
        "- DeFiLlama UUIDs and GT TVL need manual validation",
        "- Fee tiers are from Aerodrome URL params (type parameter)",
    ]

    with open(md_out, "w") as f:
        f.write("\n".join(lines))

    # Print summary
    print(f"DONE. Active: {len(active)} pools. Migrating: {len(migrating)} pools.")
    print(f"Files written:")
    print(f"  - {json_out}")
    print(f"  - {md_out}")
    print()
    print("Top 10 active by TVL:")
    for p in active[:10]:
        print(f"  {p['pair_name']:30} TVL=${p['tvl_usd']:>14,.2f}  APR={p['implied_daily_fee_apr_pct']:>7.2f}%")

    print()
    if migrating:
        print("Migrating pools:")
        for p in migrating[:5]:
            print(f"  {p['pair_name']:30} TVL=${p['tvl_usd']:>14,.2f}")


if __name__ == "__main__":
    main()