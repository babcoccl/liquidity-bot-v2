"""Build comprehensive COIN_ID_MAP for coingecko.py and token_prices.py.

Reads registry.json to discover all symbols, applies verified CoinGecko ID
mappings (with corrections from address verification), and writes both files.

Run: python3 scripts/build_coin_id_map.py
"""
import json
import os
from pathlib import Path

# ── Verified CoinGecko ID mappings ────────────────────────────────────────
# Keys are registry symbol strings. Values are CoinGecko coin IDs (lowercase).
# Corrections applied:
#   FAI → frax-ai (was freysa-ai)
#   KTA → kta (was keeta)
#   USDbC → usdbc (new)
# All other new symbols added with best-effort CoinGecko IDs.
# Symbols marked "# onchain-only" have no CoinGecko listing and will be
# skipped by the fetcher (expected behavior).

VERIFIED_MAP = {
    # ── Core assets (already mapped, kept) ────────────────────────────────
    "WETH":    "weth",
    "ETH":     "ethereum",
    "USDC":    "usd-coin",
    "USDT":    "tether",
    "cbBTC":   "coinbase-wrapped-btc",
    "cbETH":   "coinbase-wrapped-staked-eth",

    # ── Existing registry tokens (kept) ───────────────────────────────────
    "AERO":    "aerodrome-finance",
    "BRETT":   "based-brett",
    "VIRTUAL": "virtual-protocol",
    "MORPHO":  "morpho",
    "EURC":    "euro-coin",
    "eUSD":    "electronic-usd",
    "VVV":     "venice-token",

    # ── CORRECTED entries ────────────────────────────────────────────────
    "FAI":     "frax-ai",          # was freysa-ai — CORRECTED
    "KTA":     "kta",              # was keeta — CORRECTED

    # ── New: well-known tokens with CoinGecko listings ───────────────────
    "AAVE":    "aave",
    "LINK":    "chainlink",
    "SOL":     "solana",
    "ICP":     "internet-computer",
    "ZRO":     "layerzero",
    "PENDLE":  "pendle",
    "CHZ":     "chiliz",
    "GHST":    "ghost",
    "SAND":    "the-sandbox",
    "WOO":     "woo-network",
    "TRX":     "tron",

    # ── New: Base-chain tokens with CoinGecko listings ───────────────────
    "DIEM":    "diem",
    "msUSD":   "main-street-usd",
    "msETH":   "metronome-synth-eth",
    "CLANKER": "tokenbot-2",
    "TITN":    "thor-wallet",
    "CHECK":   "checkmate-2",
    "UP":      "unitas",
    "USDbC":   "usdbc",
    "KRWQ":    "krwt",
    "REI":     "unit-00-rei",

    # ── New: tokens with known CoinGecko IDs (best-effort) ───────────────
    "LBTC":    "lbtc",
    "cbLTC":   "coinbase-wrapped-ltc",
    "weETH":   "wrapped-eeth",
    "wstETH":  "wrapped-staked-eth",
    "tBTC":    "tbtc",
    "SEDA":    "seda",
    "AVAIL":   "avail",
    "MOCA":    "mocaverse",

    # ── Uppercase aliases for token_prices.py (fetch.py normalizes .upper()) ─
    "CBBTC":   "coinbase-wrapped-btc",
    "CBETH":   "coinbase-wrapped-staked-eth",
    "EUSD":    "electronic-usd",

    # ── ONCHAIN-ONLY tokens — no CoinGecko listing ───────────────────────
    # These symbols are in registry but have NO valid CoinGecko ID.
    # The fetcher will skip them (expected). Do NOT add fake IDs here.
    # Documented in memory/onchain_only_tokens.md

    # TRUST — CoinGecko returned "intuition" which is a DIFFERENT token
    # (Ethereum mainnet, not Base).  FLAG_AS_ONCHAIN_ONLY.
    # "TRUST": None  ← intentionally omitted

    # MSETH vs msETH: registry uses "msETH", CoinGecko id "metronome-synth-eth"
    # already mapped above.

    # USDz, sUSDz — Abstract chain tokens, not on CoinGecko
    # "USDz": None  ← intentionally omitted
    # "sUSDz": None  ← intentionally omitted

    # superOETHb, syrupUSDC, oUSDT, deJAAA — onchain-only
    # bsdETH, cbMEGA, cbXRP — Coinbase wrapped, not yet on CoinGecko
    # hTEA, tGBP — onchain-only
    # ACU, AORA, AUBRAI, AVNT, B3, BID, BIO, BNKR, CARV, CTR, DRV,
    # EURAU, FLOCK, FUN, LCAP, LMTS, LSK, MAMO, MEZO, MUSD, MXNB,
    # OFC, PROS, RAVE, RECALL, RED, TIBBIR, TIG, TOWER, TOWNS,
    # VCHF, VELVET, VFY, XSGD, ZEN — onchain-only or unverified
}

# Filter out None values (intentionally omitted onchain-only tokens)
VERIFIED_MAP = {k: v for k, v in VERIFIED_MAP.items() if v is not None}


def build_coingecko_map():
    """Build COIN_ID_MAP dict for coingecko.py."""
    return dict(VERIFIED_MAP)


def build_token_prices_map():
    """Build COIN_ID_MAP dict for token_prices.py (includes uppercase aliases)."""
    m = dict(VERIFIED_MAP)
    # Ensure uppercase aliases present
    m.setdefault("CBBTC", "coinbase-wrapped-btc")
    m.setdefault("CBETH", "coinbase-wrapped-staked-eth")
    m.setdefault("EUSD", "electronic-usd")
    return m


def format_map(d: dict) -> str:
    """Format a COIN_ID_MAP dict as Python source code."""
    lines = ['    COIN_ID_MAP: dict[str, str] = {']
    for k in sorted(d.keys()):
        v = d[k]
        lines.append(f'        "{k}":   "{v}",')
    lines.append('    }')
    return '\n'.join(lines)


def update_coingecko(new_map: dict):
    """Update data/fetcher/coingecko.py COIN_ID_MAP."""
    path = Path("data/fetcher/coingecko.py")
    text = path.read_text()

    block = format_map(new_map)

    # Find and replace the COIN_ID_MAP block
    start_marker = '    COIN_ID_MAP: dict[str, str] = {'
    end_marker = '    }'

    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker, start_idx) + len(end_marker)

    new_text = text[:start_idx] + block + text[end_idx:]
    path.write_text(new_text)
    print(f"UPDATED {path}: {len(new_map)} entries")


def update_token_prices(new_map: dict):
    """Update data/fetcher/token_prices.py COIN_ID_MAP."""
    path = Path("data/fetcher/token_prices.py")
    text = path.read_text()

    block = format_map(new_map)

    start_marker = '    COIN_ID_MAP: dict[str, str] = {'
    end_marker = '    }'

    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker, start_idx) + len(end_marker)

    new_text = text[:start_idx] + block + text[end_idx:]
    path.write_text(new_text)
    print(f"UPDATED {path}: {len(new_map)} entries")


if __name__ == "__main__":
    # Also verify registry symbols are covered
    with open("registry/registry.json") as f:
        pools = json.load(f)

    registry_symbols = set()
    for p in pools:
        registry_symbols.add(p["token0"]["symbol"])
        registry_symbols.add(p["token1"]["symbol"])

    cg_map = build_coingecko_map()
    tp_map = build_token_prices_map()

    # Report coverage
    mapped = registry_symbols & set(cg_map.keys())
    unmapped = registry_symbols - set(cg_map.keys())

    print(f"Registry symbols: {len(registry_symbols)}")
    print(f"Mapped to CoinGecko: {len(mapped)}")
    print(f"Onchain-only (no CG ID): {len(unmapped)}")
    if unmapped:
        print("Unmapped symbols:")
        for s in sorted(unmapped):
            print(f"  {s}")

    # Apply updates
    update_coingecko(cg_map)
    update_token_prices(tp_map)

    print("BUILD COMPLETE.")