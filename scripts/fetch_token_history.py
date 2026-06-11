"""
fetch_token_history.py — fetch 90-day hourly token price history for all
registry tokens via TokenPriceFetcher (CoinGecko). Saves to data/prices/.
Usage:
    python scripts/fetch_token_history.py [--days N] [--symbol SYM]
Options:
    --days N      Lookback window in days (default: 90)
    --symbol SYM  Fetch only this symbol (optional, for reruns)
"""
import argparse
import json
import logging
import os
import time
from pathlib import Path
from data.fetcher.coin_id_map import COIN_ID_MAP
from data.fetcher.token_prices import TokenPriceFetcher
from data.loader.token_price_loader import save_token_prices
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
REGISTRY_PATH = Path("registry/registry.json")
PRICES_DIR = Path("data/prices")
DEFAULT_DAYS = 90
def load_registry_tokens(registry_path: Path) -> dict[str, str]:
    """Return {SYMBOL_UPPER: address} for all unique tokens in registry."""
    with open(registry_path) as f:
        pools = json.load(f)
    tokens: dict[str, str] = {}
    for pool in pools.values() if isinstance(pools, dict) else pools:
        for key in ["token0", "token1"]:
            token = pool.get(key, {})
            sym = token.get("symbol", "").upper().strip()
            addr = token.get("address", "").lower().strip()
            if sym and addr:
                tokens[sym] = addr
    return tokens
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--symbol", type=str, default=None)
    args = parser.parse_args()
    api_key = os.environ.get("COINGECKO_API_KEY", "")
    fetcher = TokenPriceFetcher(api_key=api_key, rate_limit_per_min=25)
    PRICES_DIR.mkdir(parents=True, exist_ok=True)
    tokens = load_registry_tokens(REGISTRY_PATH)
    if args.symbol:
        sym = args.symbol.upper()
        if sym not in tokens:
            logger.error("Symbol %s not found in registry", sym)
            return
        tokens = {sym: tokens[sym]}
    mapped   = {s: a for s, a in tokens.items() if COIN_ID_MAP.get(s)}
    unmapped = {s: a for s, a in tokens.items() if not COIN_ID_MAP.get(s)}
    print(f"\nRegistry tokens:  {len(tokens)}")
    print(f"CoinGecko mapped: {len(mapped)}")
    print(f"Unmapped/skipped: {len(unmapped)}")
    if unmapped:
        print(f"Skipped: {', '.join(sorted(unmapped))}")
    print(f"Lookback: {args.days} days\n")
    ok, skipped, failed = 0, 0, []
    for i, (symbol, address) in enumerate(sorted(mapped.items()), 1):
        out_path = PRICES_DIR / f"{symbol}.json"
        print(f"[{i}/{len(mapped)}] {symbol:<16}", end=" ", flush=True)
        try:
            records = fetcher.fetch_token_history(symbol, address, args.days)
            if not records:
                print("EMPTY — skipped")
                skipped += 1
                continue
            save_token_prices(address, symbol, records, out_path)
            print(f"OK  {len(records)} records → {out_path.name}")
            ok += 1
        except Exception as e:
            print(f"FAILED — {e}")
            failed.append(symbol)
        time.sleep(2)
    print(f"\n{'='*50}")
    print(f"COMPLETE: {ok} OK, {skipped} empty, {len(failed)} failed")
    if failed:
        print(f"Failed tokens: {', '.join(failed)}")
    print(f"Prices written to: {PRICES_DIR}/")
if __name__ == "__main__":
    main()