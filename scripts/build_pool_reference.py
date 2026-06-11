#!/usr/bin/env python3
"""
Sprint 33-Pre: Build pool_reference.json and pool_reference.md from Sugar SDK raw data.

Reads memory/pool_reference_raw.json (already typed numbers from Sugar SDK),
cross-references against registry/registry.json, and writes final outputs.

Usage:
    python3 scripts/build_pool_reference.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main():
    raw_path = Path("memory/pool_reference_raw.json")
    registry_path = Path("registry/registry.json")
    json_out = Path("memory/pool_reference.json")
    md_out = Path("memory/pool_reference.md")

    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Run fetch_aerodrome_pools.py first.")
        sys.exit(1)

    # Load raw data (already has typed numbers from Sugar SDK)
    with open(raw_path) as f:
        raw = json.load(f)

    # Load existing registry for cross-reference
    existing_addresses = set()
    if registry_path.exists():
        try:
            with open(registry_path) as f:
                registry = json.load(f)
            # registry.json can be a bare list or a dict with "pools" key
            pool_list = registry if isinstance(registry, list) else registry.get("pools", [])
            existing_addresses = {
                p.get("pool_address", "").lower()
                for p in pool_list
            }
            print(f"Registry loaded: {len(existing_addresses)} pool addresses")
        except json.JSONDecodeError as e:
            print(f"WARN: registry.json invalid JSON ({e}). Skipping cross-reference.")
            print("      (registry.json needs repair — not blocking this build)")

    # Pass through pools — data is already clean from fetch_aerodrome_pools.py
    pools = []
    for p in raw.get("pools_raw", []):
        pool_addr = p.get("pool_address", "").lower()
        pools.append({
            "pair_name": p["pair_name"],
            "symbol": p.get("symbol", ""),
            "pool_address": pool_addr,
            "gauge_address": p.get("gauge_address", ""),
            "token0_symbol": p.get("token0_symbol", ""),
            "token1_symbol": p.get("token1_symbol", ""),
            "token0_address": p.get("token0_address", ""),
            "token1_address": p.get("token1_address", ""),
            "fee_tier_bps": p.get("fee_tier_bps", 0),
            "fee_tier_label": p.get("fee_tier_label", ""),
            "tvl_usd": p.get("tvl_usd", 0.0),
            "volume_24h_usd": p.get("volume_24h_usd", 0.0),
            "total_fees_usd": p.get("total_fees_usd", 0.0),
            "apr_pct": p.get("apr_pct", 0.0),
            "implied_daily_fees_usd": p.get("implied_daily_fees_usd", 0.0),
            "implied_daily_fee_apr_pct": p.get("implied_daily_fee_apr_pct", 0.0),
            "status": p.get("status", "active"),
            "in_registry": pool_addr in existing_addresses,
            # Placeholders for cross-validation — filled by GT/DeFiLlama passes
            "gt_tvl_usd": p.get("gt_tvl_usd"),
            "gt_volume_24h_usd": p.get("gt_volume_24h_usd"),
            "defillama_uuid": p.get("defillama_uuid", ""),
            "defillama_tvl_usd": p.get("defillama_tvl_usd"),
            "defillama_project_tag": p.get("defillama_project_tag", ""),
            "tvl_source_decision": p.get("tvl_source_decision", "Aerodrome (Sugar SDK)"),
            "notes": p.get("notes", "")
        })

    # Sort: active pools by TVL desc, then migrating at bottom
    active = sorted(
        [p for p in pools if p["status"] == "active"],
        key=lambda x: x["tvl_usd"],
        reverse=True
    )
    migrating = sorted(
        [p for p in pools if p["status"] == "migrating"],
        key=lambda x: x["tvl_usd"],
        reverse=True
    )
    pools_sorted = active + migrating

    # Count registry overlap
    in_registry_count = sum(1 for p in active if p["in_registry"])

    # Write pool_reference.json
    output = {
        "schema_version": 1,
        "scraped_at": raw.get("scraped_at", datetime.now(timezone.utc).isoformat()),
        "source": raw.get("source", "Aerodrome Sugar SDK (on-chain)"),
        "source_url": raw.get("source_url", ""),
        "chain": "Base",
        "chain_id": raw.get("chain_id", 8453),
        "protocol": "Aerodrome Slipstream",
        "total_pools": len(pools_sorted),
        "active_pools": len(active),
        "migrating_pools": len(migrating),
        "basic_excluded": raw.get("total_basic_excluded", 0),
        "in_registry_count": in_registry_count,
        "pools": pools_sorted
    }

    tmp_json = json_out.with_suffix(".tmp")
    tmp_json.write_text(json.dumps(output, indent=2))
    tmp_json.replace(json_out)

    # Write pool_reference.md
    lines = [
        "# Aerodrome Pool Reference Table",
        f"# Fetched: {raw.get('scraped_at', 'N/A')}",
        "# Chain: Base | Protocol: Aerodrome Slipstream (CL)",
        f"# Source: {raw.get('source', 'Sugar SDK')} — on-chain Sugar helper contract",
        f"# Source URL: {raw.get('source_url', '')}",
        f"# Total CL active: {len(active)} | Migrating: {len(migrating)} | Basic excluded: {raw.get('total_basic_excluded', 0)}",
        f"# In registry: {in_registry_count}/{len(active)} active pools",
        "",
        "## Active Pools (by TVL descending)",
        "",
        "| # | Pair | Symbol | Fee | TVL (USD) | 24h Vol | APR | Pool Address | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for i, p in enumerate(active, 1):
        reg_mark = "🔗" if p["in_registry"] else ""
        lines.append(
            f"| {i} | {p['pair_name']} | `{p.get('symbol', '')}` | {p['fee_tier_label']} "
            f"| ${p['tvl_usd']:>12,.2f} | ${p['volume_24h_usd']:>10,.2f} "
            f"| {p['apr_pct']:>6.2f}% | `{p['pool_address']}` | {reg_mark} active |"
        )

    lines += [
        "",
        "## Migrating Pools (Do Not Add to Registry)",
        "",
        "| # | Pair | TVL (USD) | Pool Address |",
        "|---|---|---|---|",
    ]

    for i, p in enumerate(migrating[:100], 1):
        lines.append(
            f"| {i} | {p['pair_name']} "
            f"| ${p['tvl_usd']:>12,.2f} | `{p['pool_address']}` |"
        )

    if len(migrating) > 100:
        lines.append(f"*... and {len(migrating) - 100} more migrating pools (total: {len(migrating)})")

    lines += [
        "",
        "## Notes",
        "",
        "- Data sourced from Aerodrome's on-chain Sugar helper contract via Sugar SDK",
        "- `type=-1` identifies Concentrated Liquidity (Slipstream CL) pools",
        "- `gauge_alive=False` identifies migrating pools (superseded by newer pools)",
        "- Fee tiers from `pool_fee_percentage` field (e.g., 0.3 = 0.3%)",
        "- Pool addresses and gauge addresses are on-chain contract addresses",
        "- DeFiLlama UUIDs and GT TVL need manual cross-validation (future sprints)",
    ]

    tmp_md = md_out.with_suffix(".tmp")
    tmp_md.write_text("\n".join(lines))
    tmp_md.replace(md_out)

    # Print summary
    print("=" * 60)
    print("BUILD POOL REFERENCE — COMPLETE")
    print("=" * 60)
    print(f"Active:     {len(active)} pools ({in_registry_count} in registry)")
    print(f"Migrating:  {len(migrating)} pools")
    print(f"Basic excl: {raw.get('total_basic_excluded', 0)} pools")
    print()
    print("Files written:")
    print(f"  - {json_out}")
    print(f"  - {md_out}")
    print()
    print("Top 10 active by TVL:")
    for i, p in enumerate(active[:10], 1):
        reg = " [IN REGISTRY]" if p["in_registry"] else ""
        print(f"  {i:2}. {p['pair_name']:25} TVL=${p['tvl_usd']:>12,.2f}  "
              f"APR={p['apr_pct']:>6.2f}%{reg}")

    if migrating:
        print()
        print("Top 5 migrating by TVL:")
        for p in migrating[:5]:
            print(f"      {p['pair_name']:25} TVL=${p['tvl_usd']:>12,.2f}")


if __name__ == "__main__":
    main()