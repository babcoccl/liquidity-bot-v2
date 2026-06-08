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
_AERO_SUBGRAPH_ID = "GENunSHWLBXm59mBSgPzQ8metBEp9YDfdqwFr91Tg1Qx"


def _the_graph_endpoint(api_key: str) -> str:
    """BUILD THE GRAPH ENDPOINT FOR AERODROME SUBGRAPH."""
    return (
        f"https://gateway.thegraph.com/api/{api_key}"
        f"/subgraphs/id/{_AERO_SUBGRAPH_ID}"
    )


_POOL_HOURLY_QUERY = """\
query poolHourDatas($pool: Bytes!, $periodStartUnix_gte: BigInt!) {
  poolHourDatas(
    where: {pool: $pool, periodStartUnix_gte: $periodStartUnix_gte}
    orderBy: periodStartUnix
    orderDirection: asc
  ) {
    periodStartUnix
    token0Price
    token1Price
    volumeUSD
    tvlUSD
    feeGrowthGlobal0X128
    feeGrowthGlobal1X128
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
        headers={"Content-Type": "application/json"},
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
) -> list[PoolHistoryPoint]:
    """FETCH HOURLY RECORDS FROM THE GRAPH. RETURN LIST OF PoolHistoryPoint.
    RAISE ON HTTP ERROR. RETURN EMPTY LIST IF NO DATA.
    """
    cutoff = int(time.time()) - (days * 86400)
    endpoint = _the_graph_endpoint(api_key)

    variables: dict[str, Any] = {
        "pool": pool_address.lower()[2:],
        "periodStartUnix_gte": str(cutoff),
    }

    payload = {
        "query": _POOL_HOURLY_QUERY,
        "variables": variables,
    }

    resp = _http_post(endpoint, payload)

    if "errors" in resp:
        logger.error("The Graph errors for %s: %s", pool_address, resp["errors"])
        return []

    rows = resp.get("data", {}).get("poolHourDatas", [])
    results: list[PoolHistoryPoint] = []

    for row in rows:
        ts = int(row.get("periodStartUnix", 0))
        if ts == 0:
            continue

        # token0Price IS price of token1 in token0 units
        p_t1_in_t0 = Decimal(str(row.get("token0Price", "0") or "0"))
        # token1Price IS price of token0 in token1 units
        p_t0_in_t1 = Decimal(str(row.get("token1Price", "0") or "0"))

        vol = Decimal(str(row.get("volumeUSD", "0") or "0"))
        tvl = Decimal(str(row.get("tvlUSD", "0") or "0"))

        # fee growth — raw uint256 as int, None if missing
        fg0_raw = row.get("feeGrowthGlobal0X128")
        fg1_raw = row.get("feeGrowthGlobal1X128")
        fg0 = int(fg0_raw) if fg0_raw is not None and str(fg0_raw).lstrip("-").isdigit() else None
        fg1 = int(fg1_raw) if fg1_raw is not None and str(fg1_raw).lstrip("-").isdigit() else None

        pt = PoolHistoryPoint(
            pool_address=pool_address.lower(),
            timestamp=ts,
            price_token1_in_token0=p_t1_in_t0,
            price_token0_in_token1=p_t0_in_t1,
            volume_usd=vol,
            tvl_usd=tvl,
            fee_growth_global_0=fg0,
            fee_growth_global_1=fg1,
            source="the_graph",
        )
        results.append(pt)

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
    FORMAT: { "symbol": str, "quote": "USD", "fetched_at": int, "prices": [...] }
    """
    if not prices:
        logger.warning("No price records to save for %s", symbol)
        return

    payload = {
        "symbol": symbol,
        "quote": "USD",
        "fetched_at": int(time.time()),
        "prices": prices,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(str(tmp_path), str(path))


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

    # READ API KEYS FROM ENV
    thegraph_key = os.environ.get("THEGRAPH_API_KEY", "")
    if not thegraph_key:
        logger.error(
            "THEGRAPH_API_KEY env var required. "
            "Set it in .env file or export before running."
        )
        sys.exit(1)

    coingecko_key = os.environ.get("COINGECKO_API_KEY", "")
    if not coingecko_key:
        logger.error(
            "COINGECKO_API_KEY env var required. "
            "Set it in .env file or export before running."
        )
        sys.exit(1)

    # LOAD REGISTRY
    registry = PoolRegistry(path=REGISTRY_PATH)
    registry.load()
    pools = registry.all()
    logger.info("Loaded %d pool(s) from registry", len(pools))

    # ENSURE DIRS EXIST
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    PRICES_DIR.mkdir(parents=True, exist_ok=True)

    # FETCH POOL HOURLY DATA
    for i, pool in enumerate(pools):
        try:
            logger.info(
                "Fetching pool %d/%d: %s (%s)",
                i + 1, len(pools), pool.pair_name, pool.pool_address[:10],
            )
            records = fetch_pool_hourly(
                pool_address=pool.pool_address,
                days=days,
                api_key=thegraph_key,
            )

            out_path = HISTORICAL_DIR / f"{pool.pair_name}.json"
            save_pool_history(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                records=records,
                path=out_path,
            )
            logger.info("Saved %s -> %s", pool.pair_name, out_path)

        except Exception as e:
            logger.warning(
                "FAILED to fetch pool %s (%s): %s — CONTINUING",
                pool.pair_name, pool.pool_address[:10], e,
            )

    # COLLECT UNIQUE TOKEN SYMBOLS ACROSS ALL POOLS
    token_symbols: set[str] = set()
    for pool in pools:
        token_symbols.add(pool.token0.symbol)
        token_symbols.add(pool.token1.symbol)

    logger.info("Unique token symbols to fetch: %s", sorted(token_symbols))

    # FETCH TOKEN USD PRICES
    for symbol in sorted(token_symbols):
        try:
            logger.info("Fetching prices for %s", symbol)
            prices = fetch_token_prices_usd(
                symbol=symbol,
                days=days,
                api_key=coingecko_key,
            )

            # CASE-EXACT FILENAME: cbBTC.json NOT CBBTC.json
            out_path = PRICES_DIR / f"{symbol}.json"
            save_token_prices(symbol=symbol, prices=prices, path=out_path)
            logger.info("Saved %s -> %s", symbol, out_path)

            # SLEEP 1S BETWEEN COINGECKO CALLS TO AVOID 429
            time.sleep(1)

        except Exception as e:
            logger.warning(
                "FAILED to fetch prices for %s: %s — CONTINUING", symbol, e,
            )

    logger.info("FETCH COMPLETE.")


if __name__ == "__main__":
    main()
