#!/usr/bin/env python3
"""Sprint 33-Pre: Aerodrome Pool Registry Scraper using Playwright.

Scrapes https://aerodrome.finance/liquidity for all concentrated liquidity pools,
extracting pair names, TVL, volume, fee tiers, pool addresses, and gauge addresses.

Usage:
    pip install playwright
    playwright install chromium
    python3 scripts/scrape_aerodrome_playwright.py
"""

import json
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://aerodrome.finance"
# Filtered URL: listed concentrated pools only, sorted by TVL desc
LIQUIDITY_URL = f"{BASE_URL}/liquidity?filters=listed%2Cconcentrated&sort=tvl%3Adesc"
RAW_OUTPUT = Path("memory/pool_reference_raw.json")
PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXTRACT_JS = """
() => {
    const rows = Array.from(document.querySelectorAll('a[href*="/deposit?"]'));
    function parsePool(row) {
        const href = row.getAttribute('href') || '';
        const params = new URLSearchParams((href.indexOf('?') >= 0) ? href.substring(href.indexOf('?')+1) : '');
        const text = row.textContent || '';

        // Pair name: first two token symbols separated by /
        const pairMatch = text.match(/^([A-Za-z0-9$@+]+)\\s*\\/\\s*([A-Za-z0-9$@+]+)/);
        const pair = pairMatch ? `${pairMatch[1]} / ${pairMatch[2]}` : '';

        // Fee tier: number% before pool type keyword
        const feeMatch = text.match(/(\\d+\\.?\\d*)%\\s*(?:A\\s+)?/);
        const feeTier = feeMatch ? feeMatch[1] + '%' : '';

        // Pool type label
        const typeMatch = text.match(/(Concentrated \\d+|Basic Stable|Basic Volatile)/);
        const poolType = typeMatch ? typeMatch[1] : '';

        // Migrating flag
        const isMigrating = text.includes('Migrating');

        // Volume: ~$N.NN[M/K/B] or ~$N,N,...
        const volMatch = text.match(/Volume ~\\$([\\d,.]+)[MBK]?/);
        const volumeRaw = volMatch ? volMatch[1].replace(/,/g, '') : '';

        // Fees: ~$N.NN[M/K/B] or ~$N,N,...
        const feesMatch = text.match(/Fees ~\\$([\\d,.]+)[MBK]?/);
        const feesRaw = feesMatch ? feesMatch[1].replace(/,/g, '') : '';

        // TVL: ~$N.NN[M/K/B] or ~$N,N,...
        const tvlMatch = text.match(/TVL ~\\$([\\d,.]+)[MBK]?/);
        const tvlRaw = tvlMatch ? tvlMatch[1].replace(/,/g, '') : '';

        // Fee APR
        const feeAprMatch = text.match(/Fee APR(?:\\s+)?(N\\/A|[\\d.]+)%/);
        const feeAPR = feeAprMatch ? feeAprMatch[1] : '';

        // Emission APR
        const emitAprMatch = text.match(/Emission APR(?:\\s+)?(N\\/A|[\\d.]+)%/);
        const emissionAPR = emitAprMatch ? emitAprMatch[1] : '';

        return {
            pair,
            feeTier,
            poolType,
            isMigrating,
            volumeRaw,
            feesRaw,
            tvlRaw,
            feeAPR: feeAPR === 'N/A' ? null : feeAPR,
            emissionAPR: emissionAPR === 'N/A' ? null : emissionAPR,
            token0: params.get('token0'),
            token1: params.get('token1'),
            typeParam: params.get('type'),
            factory: params.get('factory'),
            depositUrl: href
        };
    }

    return rows.map(parsePool);
}
"""


def scrape_all_pools():
    """Scrape all pool pages and return list of pool dicts."""
    all_pools = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # First load
        print("LOADING initial page...")
        page.goto(LIQUIDITY_URL, wait_until="networkidle", timeout=60_000)
        time.sleep(2)  # let JS render

        page_num = 1
        max_pages = 200  # safety cap
        min_pools_on_page = 5  # if we get fewer than this, pagination likely broke

        while page_num <= max_pages:
            print(f"SCRAPING page {page_num}...")

            # Extract pools from current page
            pools = page.evaluate(EXTRACT_JS)
            if not pools or len(pools) < min_pools_on_page:
                print(f"NO POOLS (or only {len(pools) if pools else 0}) found on page {page_num}, stopping.")
                break

            all_pools.extend(pools)
            print(f"  -> got {len(pools)} pools (total: {len(all_pools)})")

            # Find pagination container by "Showing N out of M pools" text, click its last button
            clicked = page.evaluate("""() => {
                // Find the element containing "Showing ... out of ... pools"
                const allElements = Array.from(document.querySelectorAll('*'));
                for (const el of allElements) {
                    if (el.textContent && /Showing \\d+ out of \\d+ pools/.test(el.textContent.trim())) {
                        // Don't go deeper — this is our pagination container
                        // Find the last button inside it
                        const btns = Array.from(el.querySelectorAll('button'));
                        if (btns.length > 0) {
                            const lastBtn = btns[btns.length - 1];
                            if (!lastBtn.disabled && lastBtn.offsetParent !== null) {
                                lastBtn.click();
                                return true;
                            }
                        }
                        // No valid button found in this container
                        return false;
                    }
                }
                return false;
            }""")

            if not clicked:
                print("NO NEXT button found, stopping.")
                break

            time.sleep(3)  # wait for next page to load
            page_num += 1

        browser.close()

    return all_pools


def write_output(pools):
    """Write pools to raw JSON file using atomic write."""
    tmp_path = RAW_OUTPUT.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(pools, f, indent=2)
    tmp_path.replace(RAW_OUTPUT)
    print(f"WROTE {len(pools)} pools to {RAW_OUTPUT}")


if __name__ == "__main__":
    print("=" * 60)
    print("AERODROME POOL SCRAPER — Sprint 33-Pre")
    print("=" * 60)

    pools = scrape_all_pools()

    # Filter: keep only non-migrating concentrated pools (per sprint goal)
    concentrated = [p for p in pools if "Concentrated" in p.get("poolType", "") and not p.get("isMigrating")]
    migrating = [p for p in pools if p.get("isMigrating")]
    basic = [p for p in pools if "Basic" in p.get("poolType", "")]

    print()
    print("=== SCRAPE SUMMARY ===")
    print(f"Total pools scraped: {len(pools)}")
    print(f"Concentrated (non-migrating): {len(concentrated)}")
    print(f"Migrating pools: {len(migrating)}")
    print(f"Basic pools: {len(basic)}")
    print()

    # Show top 10 by TVL (concentrated, non-migrating)
    def parse_tvl(p):
        try:
            return Decimal(p.get("tvlRaw") or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0")

    concentrated_sorted = sorted(concentrated, key=parse_tvl, reverse=True)
    print("TOP 10 CONCENTRATED POOLS BY TVL:")
    for i, p in enumerate(concentrated_sorted[:10], 1):
        print(f"  {i}. {p['pair']} | TVL: ${p['tvlRaw']} | Fee: {p['feeTier']} | Type: {p['poolType']}")

    write_output(pools)
    print()
    print("SCRAPER COMPLETE.")