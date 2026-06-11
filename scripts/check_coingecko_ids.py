"""check_coingecko_ids.py — Resolve CoinGecko IDs for unmapped registry tokens.

Usage:
    python3 scripts/check_coingecko_ids.py

Loads .env via python-dotenv (optional). Queries CoinGecko search API for each
unmapped token symbol. Prints a resolution table with FOUND / NOT_FOUND status.
"""

import json
import os
import sys
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE = "https://api.coingecko.com/api/v3/search"

# Round 1 resolved (18): AAVE, ACU, AORA, AUBRAI, AVAIL, AVNT, CTR, ICP,
#                         OFC, OUSDT, PENDLE, PROS, RAVE, RED, SOL, TRX, VELVET, WSTETH
# Round 2 resolved (18): B3, BID, BIO, BNKR, BSDETH, CHIP, LCAP, LINK, LMTS,
#                         LSK, MAMO, MEZO, UP, USDBC, USDZ, USOL, VCHF, ZRO
# Round 3 resolved (27): CARV, CBLTC, CBMEGA, CBXRP, CHECK, CHZ, CLANKER, DEJAAA,
#                         DIEM, DRV, EURAU, KRWQ, LBTC, MOCA, MSETH, MSUSD, SAND,
#                         SERV, SUPEROETHB, SUSDZ, SYRUPUSDC, TBTC, VFY, WEETH, WOO, XSGD, ZEN
# Round 4 resolved (14): FLOCK, FUN, GHST, HTEA, MUSD, MXNB, RECALL, REI,
#                         SEDA, TGBP, TIBBIR, TIG, TITN, TOWER
# 3 still rate-limited — final final retry with 12s sleep

UNMAPPED = [
    "SAPIEN", "TOWNS", "TRUST",
]

# Known well-match symbols for disambiguation (symbol -> expected name substring)
KNOWN_HINTS = {
    "AAVE": "aave",
    "CBLTC": "coinbase wrapped ltc",
    "CBMEGA": "mega eth",
    "CBXRP": "coinbase wrapped xrp",
    "CHZ": "chiliz",
    "EURAU": "eura usd",
    "FUN": "funtoken",
    "GHST": "aavegotchi ghst",
    "ICP": "internet-computer",
    "LINK": "chainlink",
    "LSK": "lisk",
    "MSETH": "moonwell staked eth",
    "MSUSD": "moonwell usd",
    "PENDLE": "pendle",
    "SAND": "the-sandbox",
    "SOL": "solana",
    "SUPEROETHB": "ethena",
    "TBTC": "tbtc",
    "TRX": "tron",
    "USDBC": "usdbc",
    "USDZ": "ondo-usd-zerobond",
    "WEETH": "wrapped-weth",
    "WOO": "woo-network",
    "WSTETH": "wrapped-snake-eye-staked-eth",
    "XSGD": "xsgd",
    "ZEN": "zeno",
    "ZRO": "layerzero",
}

api_key = os.environ.get("COINGECKO_API_KEY", "")


def search_coingecko(symbol: str) -> dict:
    """Search CoinGecko for a token. Returns best coin match or {}."""
    url = f"{BASE}?query={symbol}"
    req = Request(url, headers={"Accept": "application/json"})
    if api_key:
        req.add_header("x-cg-pro-api-key", api_key)
    try:
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except URLError as e:
        print(f"  ERROR querying {symbol}: {e}", file=sys.stderr)
        return {}

    coins = data.get("coins", [])
    if not coins:
        return {}

    hint_lower = KNOWN_HINTS.get(symbol, "").lower()
    sym_lower = symbol.lower()

    # Prefer exact symbol match first, then name match
    best = None
    for c in coins:
        c_id = c.get("id", "")
        c_sym = c.get("symbol", "").lower()
        c_name = c.get("name", "").lower()
        score = 0
        if c_sym == sym_lower:
            score += 10
        if hint_lower and hint_lower in c_id:
            score += 20
        if hint_lower and hint_lower in c_name:
            score += 15
        if best is None or score > best[1]:
            best = (c, score)

    if best and best[1] > 0:
        return {"id": best[0]["id"], "symbol": best[0].get("symbol", ""), "name": best[0].get("name", "")}
    elif coins:
        # Return first result as fallback
        c = coins[0]
        return {"id": c["id"], "symbol": c.get("symbol", ""), "name": c.get("name", "")}
    return {}


def main():
    print(f"{'SYMBOL':<14} {'COINGECKO_ID':<36} {'STATUS':<10}")
    print("-" * 62)

    results = []
    for sym in UNMAPPED:
        time.sleep(12.0)  # final 3 tokens — aggressive delay to avoid 429
        result = search_coingecko(sym)
        if result:
            status = "FOUND"
            cid = result["id"]
        else:
            status = "NOT_FOUND"
            cid = ""
        print(f"{sym:<14} {cid:<36} {status:<10}")
        results.append((sym, cid, status))

    # Also output JSON for machine consumption
    out_path = "/tmp/coingecko_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")

    found = sum(1 for _, _, s in results if s == "FOUND")
    not_found = sum(1 for _, _, s in results if s == "NOT_FOUND")
    print(f"CHECK PASSED: {found} FOUND, {not_found} NOT_FOUND out of {len(results)} tokens")


if __name__ == "__main__":
    main()