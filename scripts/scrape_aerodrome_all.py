#!/usr/bin/env python3
"""
Sprint 33-Pre: Aerodrome Pool Registry Scraper
Scrapes all concentrated liquidity pools from aerodrome.finance using Playwright.
Outputs memory/pool_reference_raw.json

Usage: python3 scripts/scrape_aerodrome_all.py
Requires: playwright (pip install playwright), playwright browsers (playwright install chromium)
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("FAILED: playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


BASE_URL = "https://aerodrome.finance/liquidity?filters=listed%2Cconcentrated&sort=tvl%3Adesc"
RAW_OUTPUT = Path("memory/pool_reference_raw.json")


def parse_usd(s: str) -> float:
    s = s.replace("$", "").replace(",", "").strip()
    multipliers = {"K": 1e3, "M": 1e6, "B": 1e9}
    for suffix, mult in multipliers.items():
        if s.upper().endswith(suffix):
            return float(s[:-1]) * mult
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_pool_data_from_snapshot(snapshot_text: str) -> list[dict]:
    """Parse a Playwright accessibility snapshot YAML to extract pool rows."""
    pools = []

    # Find all link blocks that are pool rows (they have /deposit? URLs with factory=)
    # Split by top-level link entries that match pool patterns
    lines = snapshot_text.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for link lines with /deposit? URLs containing factory=
        if "link " in line and "/deposit?" in line:
            # Extract URL params
            url_match = re.search(r'/url:\s*(.+)', line)
            url_params = {}
            if url_match:
                url_str = url_match.group(1).strip()
                for param_match in re.finditer(r'(\w+)=([^&]+)', url_str):
                    url_params[param_match.group(1)] = param_match.group(2)

            # Collect all lines for this pool block until next top-level entry
            block_lines = [line]
            j = i + 1
            while_indent = len(line) - len(line.lstrip())

            while j < len(lines):
                next_line = lines[j]
                next_indent = len(next_line) - len(next_line.lstrip()) if next_line.strip() else while_indent + 2

                # Stop if we hit a same-level or higher-level entry (new pool row)
                if next_line.strip() and next_indent <= while_indent and "link " in next_line:
                    break
                block_lines.append(next_line)
                j += 1

            block = "\n".join(block_lines)

            # Extract pair name - look for token names like "WETH / USDC"
            pair_name = ""
            # The pair is typically in the link text, e.g. "WETH / msETH"
            pair_match = re.search(r'(?:WETH|USDC|cbBTC|msETH|msUSD|AERO|EURC|USDT|LBTC|wstETH|REI|ZEN|TRX|DIEM|VVV|cbMEGA|superOETHb|sUSDz|USDz)\s*/\s*(\w+)', block)
            if not pair_match:
                # Try broader pattern
                pair_match = re.search(r'([\w]+)\s*/\s*([\w]+)', block)
            if pair_match:
                # Get the full pair from context
                full_pair = re.findall(r'([\w]+)\s*/\s*([\w]+)', block)
                for p in full_pair:
                    combined = f"{p[0]} / {p[1]}"
                    # Filter out noise like "Token Image"
                    if not any(x in combined for x in ["Image", "New", "deposit"]):
                        pair_name = combined
                        break

            # Extract fee tier - look for percentage values near the pair
            fee_tier = ""
            fee_match = re.search(r'(\d+\.?\d*)%', block)
            if fee_match:
                # Get the first fee-like value (not APR)
                fee_candidates = re.findall(r'(\d+\.?\d*)%', block)
                for fc in fee_candidates:
                    val = float(fc)
                    # Fee tiers are typically 0.005-1.0 range
                    if 0.001 <= val <= 2.0:
                        fee_tier = f"{val}%"
                        break

            # Check for "Migrating" badge
            status = "active"
            if "Migrating" in block:
                status = "migrating"

            # Extract TVL
            tvl_display = "$0"
            tvl_match = re.search(r'TVL\s+~?\$([\d,.]+(?:[KMB])?)', block)
            if tvl_match:
                tvl_display = f"${tvl_match.group(1)}"

            # Extract Volume
            vol_display = "$0"
            vol_match = re.search(r'Volume\s+~?\$([\d,.]+(?:[KMB])?)', block)
            if vol_match:
                vol_display = f"${vol_match.group(1)}"

            pools.append({
                "pair_name": pair_name,
                "tvl_display": tvl_display,
                "volume_24h_display": vol_display,
                "fee_tier_display": fee_tier,
                "status": status,
                "token0": url_params.get("token0", ""),
                "token1": url_params.get("token1", ""),
                "fee_type": url_params.get("type", ""),
                "factory": url_params.get("factory", ""),
            })

            i = j
            continue

        i += 1

    return pools


def main():
    print(f"Starting Aerodrome pool scraper at {datetime.now(timezone.utc).isoformat()}")
    print(f"URL: {BASE_URL}")

    all_pools = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Determine total pages
        print("Loading page 1...")
        page.goto(BASE_URL + "&page=1", wait_until="networkidle", timeout=60000)
        time.sleep(2)

        snapshot1 = page.accessibility.snapshot()
        # Count pools on page 1
        page1_pools = extract_pool_data_from_snapshot(snapshot1)
        print(f"Page 1: extracted {len(page1_pools)} pools")
        all_pools.extend(page1_pools)

        # Check total pool count from pagination text
        total_match = re.search(r'Showing \d+ out of (\d+) pools', snapshot1)
        total_pools_count = int(total_match.group(1)) if total_match else 940
        pools_per_page = 25
        total_pages = (total_pools_count + pools_per_page - 1) // pools_per_page
        print(f"Total pools: {total_pools_count}, Total pages: {total_pages}")

        # Paginate through remaining pages
        for page_num in range(2, total_pages + 1):
            url = f"{BASE_URL}&page={page_num}"
            print(f"Loading page {page_num}/{total_pages}...")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(2)

                snapshot = page.accessibility.snapshot()
                pools = extract_pool_data_from_snapshot(snapshot)
                print(f"  Page {page_num}: extracted {len(pools)} pools")
                all_pools.extend(pools)

            except Exception as e:
                print(f"  ERROR on page {page_num}: {e}")
                continue

        browser.close()

    # Write raw output
    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": BASE_URL,
        "total_pools_on_site": total_pools_count,
        "pages_scraped": min(len(all_pools) // 25 + 1, total_pages),
        "pools_raw": all_pools,
    }

    # Atomic write
    tmp_path = RAW_OUTPUT.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(output, f, indent=2)
    tmp_path.replace(RAW_OUTPUT)

    active = sum(1 for p in all_pools if p["status"] == "active")
    migrating = sum(1 for p in all_pools if p["status"] == "migrating")

    print(f"\n=== SCRAPE SUMMARY ===")
    print(f"Total pools extracted: {len(all_pools)}")
    print(f"Active: {active}, Migrating: {migrating}")
    print(f"Output: {RAW_OUTPUT}")
    print("SCRAPE COMPLETE.")


if __name__ == "__main__":
    main()