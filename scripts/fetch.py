"""FETCH REAL DATA FROM THE GRAPH + COINGECKO. WRITE TO DISK.
ATOMIC WRITES. READ REGISTRY. NO HARDCODED ADDRESSES.

# AUDIT:status=complete
# AUDIT:sprint=22
# AUDIT:issue=none
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from registry.registry import PoolRegistry
from data.loader.pool_loader import save_pool_history
from core.models import PoolHistoryPoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
REGISTRY_PATH = Path("registry/registry.json")
HISTORICAL_DIR = Path("data/historical")
PRICES_DIR = Path("data/prices")

# ---------------------------------------------------------------------------
# THE GRAPH — AERODROME ON BASE SUBGRAPH
# ---------------------------------------------------------------------------
_AERO_SUBGRAPH_ID = "FUbEPQw1oMghy39fwWBFY5fE6MXPXZQtjncQy2cXdrNS"


def _the_graph_endpoint(api_key: str) -> str:
    """BUILD THE GRAPH ENDPOINT FOR AERODROME SUBGRAPH."""
    return (
        f"https://gateway.thegraph.com/api/{api_key}"
        f"/subgraphs/id/{_AERO_SUBGRAPH_ID}"
    )


_POOL_HOURLY_QUERY = """\
query LiquidityPoolHourlySnapshots($pool: String!, $timestamp_gte: BigInt!) {
  liquidityPoolHourlySnapshots(
    where: {pool: $pool, timestamp_gte: $timestamp_gte}
    orderBy: timestamp
    orderDirection: asc
    first: 1000
  ) {
    timestamp
    totalValueLockedUSD
    hourlyVolumeUSD
    hourlySupplySideRevenueUSD
  }
}
"""


def _http_post(url: str, payload: dict[str, Any], timeout: int = 30) -> dict:
    """MINIMAL HTTP POST WITH urllib. NO EXTERNAL DEPS."""
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, multipart/mixed",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Origin": "https://thegraph.com",
            "Referer": "https://thegraph.com/",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("HTTP %d from %s: %s", e.code, url, body[:200])
        raise


def fetch_pool_hourly(
    pool_address: str,
    days: int,
    api_key: str,
    token0_symbol: str,
    token1_symbol: str,
    price_index: dict[str, dict[int, Decimal]],
) -> list[PoolHistoryPoint]:
    """FETCH HOURLY RECORDS FROM THE GRAPH (MESSARI SCHEMA).
    DERIVE price_token1_in_token0 FROM COINGECKO PRICE INDEX.
    RECORDS WITH NO MATCHING PRICE ENTRY ARE DROPPED.
    RAISE ON HTTP ERROR. RETURN EMPTY LIST IF NO DATA.
    """
    cutoff = int(time.time()) - (days * 86400)
    endpoint = _the_graph_endpoint(api_key)

    variables: dict[str, Any] = {
        "pool": pool_address.lower(),
        "timestamp_gte": int(cutoff),
    }

    payload = {
        "query": _POOL_HOURLY_QUERY,
        "variables": variables,
    }

    resp = _http_post(endpoint, payload)

    if "errors" in resp:
        logger.error("The Graph errors for %s: %s", pool_address, resp["errors"])
        return []

    rows = resp.get("data", {}).get("liquidityPoolHourlySnapshots", [])

    t0_prices = price_index.get(token0_symbol, {})
    t1_prices = price_index.get(token1_symbol, {})

    results: list[PoolHistoryPoint] = []
    dropped = 0

    for row in rows:
        ts = int(row.get("timestamp", 0))
        if ts == 0:
            continue

        p0_usd = t0_prices.get(ts)
        p1_usd = t1_prices.get(ts)

        if p0_usd is None or p1_usd is None:
            # Try nearest hour within ±1800s (30 min)
            if t0_prices and p0_usd is None:
                nearest = min(t0_prices, key=lambda t: abs(t - ts))
                if abs(nearest - ts) <= 1800:
                    p0_usd = t0_prices[nearest]
            if t1_prices and p1_usd is None:
                nearest = min(t1_prices, key=lambda t: abs(t - ts))
                if abs(nearest - ts) <= 1800:
                    p1_usd = t1_prices[nearest]

        if p0_usd is None or p1_usd is None:
            dropped += 1
            continue

        # Derive ratio prices from USD values
        if p0_usd > Decimal("0"):
            p_t1_in_t0 = p1_usd / p0_usd
        else:
            p_t1_in_t0 = Decimal("0")

        if p1_usd > Decimal("0"):
            p_t0_in_t1 = p0_usd / p1_usd
        else:
            p_t0_in_t1 = Decimal("0")

        vol = Decimal(str(row.get("hourlyVolumeUSD", "0") or "0"))
        tvl = Decimal(str(row.get("totalValueLockedUSD", "0") or "0"))

        pt = PoolHistoryPoint(
            pool_address=pool_address.lower(),
            timestamp=ts,
            price_token1_in_token0=p_t1_in_t0,
            price_token0_in_token1=p_t0_in_t1,
            volume_usd=vol,
            tvl_usd=tvl,
            fee_growth_global_0=None,
            fee_growth_global_1=None,
            source="the_graph",
        )
        results.append(pt)

    if dropped:
        logger.warning(
            "fetch_pool_hourly: dropped %d records with no price match for %s",
            dropped, pool_address[:10],
        )

    logger.info("Fetched %d hourly records for %s", len(results), pool_address[:8])
    return sorted(results, key=lambda r: r.timestamp)


# ---------------------------------------------------------------------------
# COINGECKO — TOKEN USD PRICES
# ---------------------------------------------------------------------------
_COINGECKO_IDS: dict[str, str] = {
    "WETH": "weth",
    "USDC": "usd-coin",
    "USDT": "tether",
    "cbBTC": "coinbase-wrapped-btc",
}


def fetch_token_prices_usd(
    symbol: str,
    days: int,
    api_key: str,
) -> list[dict]:
    """FETCH TOKEN PRICE HISTORY FROM COINGECKO. RETURN LIST OF PRICE DICTS.
    EACH DICT: { "timestamp": int, "price_usd": str }
    RAISE ON HTTP ERROR. RETURN EMPTY LIST IF SYMBOL NOT IN _COINGECKO_IDS.
    API KEY IS OPTIONAL — FREE TIER WORKS WITHOUT IT.
    """
    import urllib.request
    import urllib.error

    coin_id = _COINGECKO_IDS.get(symbol)
    if coin_id is None:
        logger.warning("No CoinGecko ID for symbol=%s — SKIP", symbol)
        return []

    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        f"?vs_currency=usd&days={days}&interval=hourly"
    )

    headers: dict[str, str] = {"Accept": "application/json"}
    if api_key:
        headers["x-cg-demo-api-key"] = api_key

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("CoinGecko HTTP %d for %s: %s", e.code, symbol, body[:200])
        raise

    raw_prices = data.get("prices", [])
    results: list[dict] = []

    for entry in raw_prices:
        ts_ms = int(entry[0])
        price_float = float(entry[1])
        # ONE PERMITTED FLOAT-TO-DECIMAL CONVERSION
        price_usd = Decimal(str(price_float))
        results.append({
            "timestamp": ts_ms // 1000,
            "price_usd": str(price_usd),
        })

    logger.info("Fetched %d price points for %s", len(results), symbol)
    return results


def save_token_prices(
    symbol: str,
    prices: list[dict],
    path: Path,
) -> None:
    """WRITE TOKEN PRICE FILE. ATOMIC WRITE.
    FORMAT MATCHES token_price_loader.load_token_prices() SCHEMA.
    { "token_address": "", "symbol": str, "fetched_at": int, "records": [...] }
    EACH RECORD: { "timestamp": int, "price_usd": str, "volume_usd": "0",
                   "market_cap_usd": null, "source": "coingecko" }
    """
    if not prices:
        logger.warning("No price records to save for %s", symbol)
        return

    records = [
        {
            "timestamp": p["timestamp"],
            "price_usd": p["price_usd"],
            "volume_usd": "0",
            "market_cap_usd": None,
            "source": "coingecko",
        }
        for p in prices
    ]

    payload = {
        "token_address": "",
        "symbol": symbol,
        "fetched_at": int(time.time()),
        "records": records,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(str(tmp_path), str(path))


def _build_price_index(
    prices_dir: Path,
    token0_symbol: str,
    token1_symbol: str,
) -> dict[str, dict[int, Decimal]]:
    """BUILD TIMESTAMP->PRICE_USD INDEX FOR TWO TOKENS FROM DISK.
    RETURNS { symbol: { timestamp_int: Decimal(price_usd) } }.
    RETURNS EMPTY INNER DICT IF FILE MISSING OR UNPARSEABLE.
    CALLED AFTER TOKEN PRICE FILES ARE WRITTEN TO DISK.
    """
    index: dict[str, dict[int, Decimal]] = {}
    for symbol in (token0_symbol, token1_symbol):
        path = prices_dir / f"{symbol}.json"
        try:
            raw = json.loads(path.read_text())
            records = raw.get("records", [])
            index[symbol] = {
                int(r["timestamp"]): Decimal(str(r["price_usd"]))
                for r in records
                if r.get("price_usd") is not None
            }
            logger.info(
                "_build_price_index: %s — %d entries", symbol, len(index[symbol])
            )
        except Exception as e:
            logger.warning(
                "_build_price_index: failed to load %s: %s", symbol, e
            )
            index[symbol] = {}
    return index


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    """PARSE CLI ARGS. --days N."""
    parser = argparse.ArgumentParser(description="Fetch pool + token data")
    parser.add_argument(
        "--days", type=int, default=30,
        help="Number of days of history to fetch (default: 30)",
    )
    return parser.parse_args()


def main() -> None:
    """FETCH ALL POOLS + TOKENS. WRITE TO DISK. LOG PROGRESS."""
    logging.basicConfig(level=logging.INFO)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    args = parse_args()
    days = args.days

    # THEGRAPH KEY IS REQUIRED — AUTHENTICATED ENDPOINT
    thegraph_key = os.environ.get("THEGRAPH_API_KEY", "")
    if not thegraph_key:
        logger.error(
            "THEGRAPH_API_KEY env var required. "
            "Set it in .env file or export before running."
        )
        sys.exit(1)

    # COINGECKO KEY IS OPTIONAL — FREE TIER WORKS WITHOUT IT
    coingecko_key = os.environ.get("COINGECKO_API_KEY", "")
    if not coingecko_key:
        logger.info("COINGECKO_API_KEY not set — using free tier (no key)")

    # LOAD REGISTRY
    registry = PoolRegistry(path=REGISTRY_PATH)
    registry.load()
    pools = registry.all()
    logger.info("Loaded %d pool(s) from registry", len(pools))

    # ENSURE DIRS EXIST
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    PRICES_DIR.mkdir(parents=True, exist_ok=True)

    # COLLECT UNIQUE TOKEN SYMBOLS ACROSS ALL POOLS — BEFORE FETCH
    token_symbols: set[str] = set()
    for pool in pools:
        token_symbols.add(pool.token0.symbol)
        token_symbols.add(pool.token1.symbol)

    logger.info("Unique token symbols to fetch: %s", sorted(token_symbols))

    # FETCH TOKEN USD PRICES FIRST — NEEDED FOR PRICE INDEX
    for symbol in sorted(token_symbols):
        try:
            logger.info("Fetching prices for %s", symbol)
            prices = fetch_token_prices_usd(
                symbol=symbol,
                days=days,
                api_key=coingecko_key,
            )
            out_path = PRICES_DIR / f"{symbol}.json"
            save_token_prices(symbol=symbol, prices=prices, path=out_path)
            logger.info("Saved %s -> %s", symbol, out_path)
            time.sleep(1)
        except Exception as e:
            logger.warning(
                "FAILED to fetch prices for %s: %s — CONTINUING", symbol, e
            )

    # FETCH POOL HOURLY DATA — TOKENS MUST BE ON DISK FIRST
    for i, pool in enumerate(pools):
        try:
            logger.info(
                "Fetching pool %d/%d: %s (%s)",
                i + 1, len(pools), pool.pair_name, pool.pool_address[:10],
            )

            # BUILD PRICE INDEX FROM DISK FOR THIS POOL'S TOKENS
            price_index = _build_price_index(
                prices_dir=PRICES_DIR,
                token0_symbol=pool.token0.symbol,
                token1_symbol=pool.token1.symbol,
            )

            t0_count = len(price_index.get(pool.token0.symbol, {}))
            t1_count = len(price_index.get(pool.token1.symbol, {}))
            if t0_count == 0 or t1_count == 0:
                logger.warning(
                    "PRICE INDEX EMPTY for %s (t0=%d, t1=%d) — pool will have 0 records",
                    pool.pair_name, t0_count, t1_count,
                )

            records = fetch_pool_hourly(
                pool_address=pool.pool_address,
                days=days,
                api_key=thegraph_key,
                token0_symbol=pool.token0.symbol,
                token1_symbol=pool.token1.symbol,
                price_index=price_index,
            )

            out_path = HISTORICAL_DIR / f"{pool.pair_name}.json"
            save_pool_history(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                records=records,
                path=out_path,
            )
            logger.info("Saved %s -> %s (%d records)", pool.pair_name, out_path, len(records))

        except Exception as e:
            logger.warning(
                "FAILED to fetch pool %s (%s): %s — CONTINUING",
                pool.pair_name, pool.pool_address[:10], e,
            )

    # STRUCTURED SUMMARY — PASTE-FRIENDLY FOR REVIEW
    print("=== FETCH SUMMARY ===")
    for hfile in sorted(HISTORICAL_DIR.glob("*.json")):
        try:
            d = json.loads(hfile.read_text())
            n = len(d.get("records", []))
            print(f"  {hfile.name:<22} N={n:>4} hourly records")
        except Exception:
            print(f"  {hfile.name:<22} PARSE ERROR")
    for pfile in sorted(PRICES_DIR.glob("*.json")):
        try:
            d = json.loads(pfile.read_text())
            n = len(d.get("records", []))
            print(f"  {pfile.name:<22} N={n:>4} price points")
        except Exception:
            print(f"  {pfile.name:<22} PARSE ERROR")
    print("FETCH COMPLETE.")


if __name__ == "__main__":
    main()