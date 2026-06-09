"""CHECK GECKOTERMINAL API CONNECTIVITY AND POOL COVERAGE.

Run this before fetch.py to verify:
  1. GeckoTerminal API is reachable (no key required)
  2. All registry pools are indexed on Base network
  3. OHLCV endpoint returns candles for each pool (N > 0)

Usage:
    python scripts/check_geckoterminal.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_GT_BASE_URL = "https://api.geckoterminal.com/api/v2"
_GT_NETWORK = "base"
_REGISTRY_PATH = Path("registry/registry.json")
_TIMEOUT = 15
_HEADERS = {
    "Accept": "application/json;version=20230302",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _get(url: str, params: dict | None = None) -> dict:
    full_url = url + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(full_url, headers=_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
        return json.loads(r.read())


def main() -> int:
    failures: list[str] = []

    # CHECK 1: GeckoTerminal ping
    try:
        data = _get(f"{_GT_BASE_URL}/networks/{_GT_NETWORK}/pools",
                    {"page": 1})
        pool_count = len(data.get("data", []))
        print(f"[1] PING: OK (top pools returned: {pool_count})")
    except Exception as e:
        failures.append(f"PING failed: {e}")
        print(f"[1] PING: FAILED — {e}")
        print("CHECK FAILED: cannot reach GeckoTerminal API")
        return 1

    # CHECK 2: Load registry
    try:
        raw = json.loads(_REGISTRY_PATH.read_text())
        pools = raw.get("pools", [])
        if not pools:
            failures.append("Registry has 0 pools")
            print("[2] REGISTRY: FAILED — 0 pools found")
        else:
            print(f"[2] REGISTRY: OK ({len(pools)} pool(s))")
    except Exception as e:
        failures.append(f"Registry load failed: {e}")
        print(f"[2] REGISTRY: FAILED — {e}")
        print("CHECK FAILED: cannot load registry")
        return 1

    # CHECK 3: OHLCV endpoint for each pool
    for pool in pools:
        addr = pool.get("pool_address", "").lower()
        pair = pool.get("pair_name", addr[:10])
        url = (
            f"{_GT_BASE_URL}/networks/{_GT_NETWORK}"
            f"/pools/{addr}/ohlcv/hour"
        )
        try:
            data = _get(url, {"aggregate": 1, "limit": 10,
                               "currency": "usd", "token": "base"})
            candles = (
                data.get("data", {})
                    .get("attributes", {})
                    .get("ohlcv_list", [])
            )
            if candles:
                latest_ts = int(candles[0][0])
                latest_close = candles[0][4]
                print(
                    f"[3] {pair:<16} OK  "
                    f"candles=10  "
                    f"latest_close={latest_close:.6f}  "
                    f"ts={latest_ts}"
                )
            else:
                failures.append(f"{pair}: 0 candles returned")
                print(f"[3] {pair:<16} FAILED — 0 candles returned")
        except urllib.error.HTTPError as e:
            failures.append(f"{pair}: HTTP {e.code}")
            print(f"[3] {pair:<16} FAILED — HTTP {e.code}")
        except Exception as e:
            failures.append(f"{pair}: {type(e).__name__}: {e}")
            print(f"[3] {pair:<16} FAILED — {type(e).__name__}: {e}")

        time.sleep(0.5)  # 30 req/min rate limit = ~2/s max; 0.5s is safe

    if failures:
        print()
        for f in failures:
            print(f"CHECK FAILED: {f}")
        return 1

    print()
    print(
        f"CHECK PASSED: GeckoTerminal reachable, "
        f"all {len(pools)} pool(s) return OHLCV data"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())