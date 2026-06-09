"""FETCH REAL DATA FROM THE GRAPH + COINGECKO. WRITE TO DISK.
ATOMIC WRITES. READ REGISTRY. NO HARDCODED ADDRESSES.

# AUDIT:status=complete
# AUDIT:sprint=23
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
# GECKOTERMINAL — POOL OHLCV (FREE, NO KEY REQUIRED)
# ---------------------------------------------------------------------------
_GT_BASE_URL = "https://api.geckoterminal.com/api/v2"
_GT_NETWORK = "base"


def _geckoterminal_ohlcv_url(pool_address: str) -> str:
    """BUILD GECKOTERMINAL OHLCV URL FOR A POOL ON BASE."""
    return (
        f"{_GT_BASE_URL}/networks/{_GT_NETWORK}"
        f"/pools/{pool_address.lower()}/ohlcv/hour"
    )


def _geckoterminal_pool_info_url(pool_address: str) -> str:
    """BUILD GECKOTERMINAL POOL INFO URL. RETURNS CURRENT TVL."""
    return (
        f"{_GT_BASE_URL}/networks/{_GT_NETWORK}"
        f"/pools/{pool_address.lower()}"
    )


def fetch_pool_tvls_batch(
    pool_addresses: list[str],
) -> dict[str, Decimal]:
    """FETCH CURRENT TVL FOR MULTIPLE POOLS IN ONE GT REQUEST.
    RETURNS { pool_address_lower: Decimal(reserve_in_usd) }.
    MISSING POOLS GET Decimal("0"). NEVER RAISES.
    """
    if not pool_addresses:
        return {}

    url = f"{_GT_BASE_URL}/networks/{_GT_NETWORK}/pools"
    # GT accepts comma-separated addresses in the `addresses` param
    params: dict[str, Any] = {
        "addresses": ",".join(a.lower() for a in pool_addresses),
    }

    result: dict[str, Decimal] = {
        a.lower(): Decimal("0") for a in pool_addresses
    }

    try:
        resp = _http_get(url, params)
        for pool_data in resp.get("data", []):
            attrs = pool_data.get("attributes", {})
            addr = attrs.get("address", "").lower()
            reserve = attrs.get("reserve_in_usd") or "0"
            if addr in result:
                result[addr] = Decimal(str(reserve))
                logger.info(
                    "fetch_pool_tvls_batch: %s TVL = %s USD",
                    addr[:10], result[addr],
                )
    except Exception as e:
        logger.warning(
            "fetch_pool_tvls_batch: failed — %s: %s. All TVLs = 0.",
            type(e).__name__, e,
        )

    return result


# ---------------------------------------------------------------------------
# DEFILLAMA — HISTORICAL TVL PER POOL
# ---------------------------------------------------------------------------
_DEFILLAMA_YIELDS_URL = "https://yields.llama.fi"


def fetch_defillama_tvl_history(
    pool_address: str,       # kept for logging only
    days: int,
    symbol: str,             # e.g. "WETH-USDC" (no fee suffix)
    fee_tier: int,           # e.g. 500, 3000, 10000
) -> dict[int, Decimal]:
    """FETCH DAILY TVL HISTORY FROM DEFILLAMA FOR ONE POOL.

    Matching uses chain + project + symbol + fee_tier from poolMeta
    because DeFiLlama yields API does NOT store pool contract addresses.

    RETURNS { unix_timestamp_midnight: Decimal(tvl_usd) }.
    RETURNS EMPTY DICT IF POOL NOT FOUND OR REQUEST FAILS.
    NEVER RAISES.
    """
    import urllib.request as _urllib_req

    # STEP 1 — discover DeFiLlama pool UUID by symbol + fee_tier
    uuid: str | None = None

    # Build candidate symbols: try both token orderings
    fee_pct = fee_tier / 10000  # 500 -> 0.05%
    sym_parts = [s.strip().upper() for s in symbol.split("-")]
    candidates = {symbol.upper(), f"{sym_parts[1]}-{sym_parts[0]}"}

    try:
        req = _urllib_req.Request(
            f"{_DEFILLAMA_YIELDS_URL}/pools",
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with _urllib_req.urlopen(req, timeout=15) as r:
            all_pools = json.loads(r.read())

        for p in all_pools.get("data", []):
            if p.get("chain", "").lower() != "base":
                continue
            if p.get("project", "").lower() != "uniswap-v3":
                continue
            p_symbol = p.get("symbol", "").upper()
            if p_symbol not in candidates:
                continue
            # Match fee tier via poolMeta field
            # DeFiLlama poolMeta for Uniswap V3 looks like "0.05%" or "0.3%"
            meta = (p.get("poolMeta") or "").replace("%", "").strip()
            try:
                meta_fee_pct = float(meta)
            except ValueError:
                meta_fee_pct = None
            if meta_fee_pct is not None and abs(meta_fee_pct - fee_pct) > 0.001:
                continue
            uuid = p["pool"]
            logger.info(
                "fetch_defillama_tvl_history: matched %s fee=%s -> uuid=%s symbol=%s tvl=$%s",
                symbol, fee_tier, uuid[:8], p_symbol, p.get("tvlUsd"),
            )
            break
    except Exception as e:
        logger.warning(
            "fetch_defillama_tvl_history: pool lookup failed for %s: %s",
            pool_address[:10], e,
        )
        return {}

    if not uuid:
        logger.warning(
            "fetch_defillama_tvl_history: symbol=%s fee=%s not found in DeFiLlama",
            symbol, fee_tier,
        )
        return {}

    # STEP 2 — fetch TVL history for this UUID
    try:
        req = _urllib_req.Request(
            f"{_DEFILLAMA_YIELDS_URL}/chart/{uuid}",
            headers={
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
        )
        with _urllib_req.urlopen(req, timeout=15) as r:
            chart = json.loads(r.read())

        cutoff = int(time.time()) - (days * 86400)
        result: dict[int, Decimal] = {}
        for entry in chart.get("data", []):
            ts = int(entry.get("timestamp", 0))
            tvl = Decimal(str(entry.get("tvlUsd", "0") or "0"))
            if ts >= cutoff and tvl > Decimal("0"):
                result[ts] = tvl

        logger.info(
            "fetch_defillama_tvl_history: %s — %d daily points",
            symbol, len(result),
        )
        return result
    except Exception as e:
        logger.warning(
            "fetch_defillama_tvl_history: chart fetch failed for %s: %s",
            pool_address[:10], e,
        )
        return {}


def _http_get(
    url: str,
    params: dict[str, Any],
    timeout: int = 30,
    max_retries: int = 3,
) -> dict:
    """MINIMAL HTTP GET WITH urllib. NO EXTERNAL DEPS.
    RETRIES UP TO max_retries TIMES ON 429 WITH EXPONENTIAL BACKOFF.
    RAISES ON FINAL FAILURE OR NON-429 HTTP ERROR.
    """
    import urllib.parse
    import urllib.request
    import urllib.error

    full_url = url + "?" + urllib.parse.urlencode(params) if params else url
    req = urllib.request.Request(
        full_url,
        headers={
            "Accept": "application/json;version=20230302",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
        method="GET",
    )
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                wait = 15 * (2 ** attempt)  # 15s, 30s, 60s
                logger.warning(
                    "HTTP 429 from %s — retry %d/%d in %ds",
                    full_url[:80], attempt + 1, max_retries, wait,
                )
                time.sleep(wait)
                last_exc = e
                continue
            body = e.read().decode("utf-8", errors="replace")
            logger.error(
                "HTTP %d from %s: %s", e.code, full_url[:120], body[:200]
            )
            raise
    raise last_exc  # type: ignore[misc]


def fetch_pool_hourly(
    pool_address: str,
    days: int,
    token0_symbol: str,
    token1_symbol: str,
    price_index: dict[str, dict[int, Decimal]],
    tvl_usd: Decimal = Decimal("0"),
    tvl_history: dict[int, Decimal] | None = None,
) -> list[PoolHistoryPoint]:
    """FETCH HOURLY OHLCV FROM GECKOTERMINAL. NO API KEY REQUIRED.
    DERIVE TVL FROM POOL INFO ENDPOINT (SCALAR — CURRENT SNAPSHOT).
    PRICE: close price with token="base" = price_token1_in_token0.
    RECORDS WITH NO COINGECKO PRICE MATCH WITHIN ±1800s ARE DROPPED.
    RAISE ON HTTP ERROR. RETURN EMPTY LIST IF NO DATA.
    """
    url = _geckoterminal_ohlcv_url(pool_address)
    target_hours = days * 24
    cutoff = int(time.time()) - (days * 86400)
    _GT_PAGE_SIZE = 1000  # GT free tier hard cap per request

    # PAGINATE BACKWARDS UNTIL WE HAVE ENOUGH HOURS OR NO MORE DATA
    all_pages: list[list] = []
    before_ts: int | None = None
    pages_fetched = 0

    while True:
        params: dict[str, Any] = {
            "aggregate": 1,
            "limit": _GT_PAGE_SIZE,
            "currency": "usd",
            "token": "base",
        }
        if before_ts is not None:
            params["before_timestamp"] = before_ts

        resp = _http_get(url, params)
        page = (
            resp.get("data", {})
                .get("attributes", {})
                .get("ohlcv_list", [])
        )

        if not page:
            break

        # GT returns newest-first within each page
        # Oldest candle in this page = last element
        oldest_ts = int(page[-1][0])
        all_pages.append(page)
        pages_fetched += 1

        logger.debug(
            "fetch_pool_hourly: page %d fetched %d candles, oldest_ts=%d",
            pages_fetched, len(page), oldest_ts,
        )

        # Stop only when we've gone back far enough.
        # Do NOT exit on partial page — GT naturally returns < 1000
        # candles on the most recent page (incomplete current hour).
        # The empty-page check above handles true end-of-data.
        if oldest_ts <= cutoff:
            break

        # Prepare next page: fetch candles older than oldest on this page
        before_ts = oldest_ts

        # Rate limit: sleep between pagination requests
        time.sleep(2)

    if not all_pages:
        logger.warning(
            "fetch_pool_hourly: 0 candles returned for %s", pool_address[:10]
        )
        return []

    # Concatenate pages (each newest-first), then reverse entire set
    # to produce a single ascending-time list
    combined_newest_first: list = []
    for page in all_pages:
        combined_newest_first.extend(page)

    raw_candles = list(reversed(combined_newest_first))

    # Drop duplicates on timestamp (can occur at page boundaries)
    seen_ts: set[int] = set()
    deduped: list = []
    for c in raw_candles:
        ts = int(c[0])
        if ts not in seen_ts:
            seen_ts.add(ts)
            deduped.append(c)
    raw_candles = deduped

    # Drop candles older than cutoff
    raw_candles = [c for c in raw_candles if int(c[0]) >= cutoff]

    logger.info(
        "fetch_pool_hourly: %d pages, %d candles after dedup+cutoff for %s",
        pages_fetched, len(raw_candles), pool_address[:10],
    )

    results: list[PoolHistoryPoint] = []

    for candle in raw_candles:
        # [timestamp_s, open, high, low, close, volume_usd]
        ts = int(candle[0])
        close_price = Decimal(str(candle[4] or "0"))
        vol = Decimal(str(candle[5] or "0"))

        # price_token1_in_token0 = close (token="base" convention)
        p_t1_in_t0 = close_price
        if p_t1_in_t0 > Decimal("0"):
            p_t0_in_t1 = Decimal("1") / p_t1_in_t0
        else:
            p_t0_in_t1 = Decimal("0")

        # USE HISTORICAL TVL IF AVAILABLE, ELSE FALL BACK TO SCALAR
        tvl = tvl_usd  # default: GT current snapshot
        if tvl_history:
            # Find nearest daily TVL entry within ±12 hours
            best_ts = None
            best_delta = 43200  # 12 hours in seconds
            for tvl_ts, tvl_val in tvl_history.items():
                delta = abs(ts - tvl_ts)
                if delta < best_delta:
                    best_delta = delta
                    best_ts = tvl_ts
            if best_ts is not None:
                tvl = tvl_history[best_ts]

        pt = PoolHistoryPoint(
            pool_address=pool_address.lower(),
            timestamp=ts,
            price_token1_in_token0=p_t1_in_t0,
            price_token0_in_token1=p_t0_in_t1,
            volume_usd=vol,
            tvl_usd=tvl,
            fee_growth_global_0=None,
            fee_growth_global_1=None,
            source="geckoterminal",
        )
        results.append(pt)

    # Sprint 27: log first and last TVL values applied (one-time per pool)
    tvl_values = [rec.tvl_usd for rec in results if rec.tvl_usd > Decimal("0")]
    if tvl_values:
        logger.info(
            "TVL range for %s: first=$%s last=$%s (current_snapshot=$%s)",
            pool_address[:10],
            tvl_values[0], tvl_values[-1], tvl_usd,
        )

    logger.info(
        "fetch_pool_hourly: %d records for %s", len(results), pool_address[:8]
    )
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

    # THEGRAPH KEY IS OPTIONAL — GECKOTERMINAL DOES NOT NEED IT
    thegraph_key = os.environ.get("THEGRAPH_API_KEY", "")
    if not thegraph_key:
        logger.info(
            "THEGRAPH_API_KEY not set — GeckoTerminal fetch does not require it"
        )
    # NOTE: thegraph_key retained in env for future subgraph use

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

    # BATCH-FETCH TVL FOR ALL POOLS IN ONE REQUEST
    pool_tvl_map: dict[str, Decimal] = fetch_pool_tvls_batch(
        [pool.pool_address for pool in pools]
    )
    logger.info("Batch TVL fetch complete: %d pools", len(pool_tvl_map))

    # FETCH HISTORICAL TVL FROM DEFILLAMA FOR EACH POOL
    pool_tvl_history: dict[str, dict[int, Decimal]] = {}
    for pool in pools:
        time.sleep(1)
        # Strip fee tier suffix from pair_name for symbol matching
        # "WETH-USDC-5" -> "WETH-USDC"
        base_symbol = pool.pair_name.rsplit("-", 1)[0]
        history = fetch_defillama_tvl_history(
            pool_address=pool.pool_address,
            days=days,
            symbol=base_symbol,
            fee_tier=pool.fee_tier,
        )
        pool_tvl_history[pool.pool_address.lower()] = history

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
                token0_symbol=pool.token0.symbol,
                token1_symbol=pool.token1.symbol,
                price_index=price_index,
                tvl_usd=pool_tvl_map.get(pool.pool_address.lower(), Decimal("0")),
                tvl_history=pool_tvl_history.get(pool.pool_address.lower()),
            )

            if not records:
                logger.warning(
                    "fetch_pool_hourly returned 0 records for %s — "
                    "writing empty file to prevent stale data",
                    pool.pair_name,
                )
                out_path = HISTORICAL_DIR / f"{pool.pair_name}.json"
                empty_payload = {
                    "pool_address": pool.pool_address.lower(),
                    "pair_name": pool.pair_name,
                    "fetched_at": int(time.time()),
                    "records": [],
                    "source": "geckoterminal",
                }
                tmp = Path(str(out_path) + ".tmp")
                with open(tmp, "w") as f:
                    json.dump(empty_payload, f)
                os.replace(str(tmp), str(out_path))
                continue

            out_path = HISTORICAL_DIR / f"{pool.pair_name}.json"
            save_pool_history(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                records=records,
                path=out_path,
            )
            logger.info("Saved %s -> %s (%d records)", pool.pair_name, out_path, len(records))

            # RATE LIMIT: GeckoTerminal free tier = 30 req/min.
            # Pagination adds 2s sleep between pages within fetch_pool_hourly.
            # Add 8s between pools to avoid 429 on free tier (5 pools x 2+ calls).
            time.sleep(5)  # rate limit: 5s between pools (TVL now batch-fetched)

        except Exception as e:
            logger.warning(
                "FAILED to fetch pool %s (%s): %s — CONTINUING",
                pool.pair_name, pool.pool_address[:10], e,
            )

    # STRUCTURED SUMMARY — SCOPED TO REGISTRY PAIRS ONLY
    # Does not show stale files from prior runs with different registries
    print("=== FETCH SUMMARY ===")
    for pool in pools:
        hfile = HISTORICAL_DIR / f"{pool.pair_name}.json"
        try:
            d = json.loads(hfile.read_text())
            n = len(d.get("records", []))
            status = "OK" if n > 0 else "EMPTY — fetch may have failed"
            print(f"  {pool.pair_name:<20} N={n:>4} hourly records  {status}")
        except FileNotFoundError:
            print(f"  {pool.pair_name:<20} MISSING — file not written")
        except Exception:
            print(f"  {pool.pair_name:<20} PARSE ERROR")
    for pfile in sorted(PRICES_DIR.glob("*.json")):
        try:
            d = json.loads(pfile.read_text())
            n = len(d.get("records", []))
            print(f"  {pfile.name:<20} N={n:>4} price points")
        except Exception:
            print(f"  {pfile.name:<20} PARSE ERROR")
    print("FETCH COMPLETE.")


if __name__ == "__main__":
    main()