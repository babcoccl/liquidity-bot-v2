"""
GeckoTerminalFetcher — primary data source.
Fetches hourly OHLCV from GeckoTerminal public API.
Paginates using before_timestamp cursor.
fee_growth_global fields always None (source cannot provide).
tvl_usd sourced from pool detail endpoint (reserve_in_usd).
"""
# AUDIT:status=complete
# AUDIT:sprint=9

import logging
import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolHistoryPoint

logger = logging.getLogger(__name__)

_BASE = "https://api.geckoterminal.com/api/v2"
_INTER_POOL_SLEEP = 10.0
_INTER_PAGE_SLEEP = 2.0
_BACKOFFS = [15, 30, 60, 120, 240]


class GeckoTerminalFetcher(AbstractFetcher):
    """Fetches pool OHLCV history from GeckoTerminal API on Base network."""

    name: str = "gecko_terminal"

    def __init__(
        self,
        network: str = "base",
        timeframe: str = "hour",
        rate_limit_per_min: int = 25,
    ):
        self.network = network
        self.timeframe = timeframe
        self.rate_limit_per_min = rate_limit_per_min
        self._request_timestamps: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_pool_history(self, pool_address: str, days: int) -> list[PoolHistoryPoint]:
        """Fetch up to `days` of hourly OHLCV data for the given pool address."""
        pool_address = pool_address.lower().strip()

        logger.info(
            "GeckoTerminalFetcher: sleeping %.1fs before first request for %s",
            _INTER_POOL_SLEEP, pool_address
        )
        time.sleep(_INTER_POOL_SLEEP)

        tvl_usd = self._fetch_tvl(pool_address)

        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=days)
        cutoff_ts = int(cutoff_dt.timestamp())

        url = f"{_BASE}/networks/{self.network}/pools/{pool_address}/ohlcv/{self.timeframe}"
        headers = {"User-Agent": "liquidity-bot-v2/1.0", "Accept": "application/json"}

        all_rows: list[list] = []
        before_ts: Optional[int] = None
        first_page = True

        while True:
            params: dict = {"limit": 1000}
            if before_ts is not None:
                params["before_timestamp"] = before_ts

            if not first_page:
                time.sleep(_INTER_PAGE_SLEEP)
            first_page = False

            resp = self._get(url, headers, params)
            page_data: list = (
                resp.json()
                .get("data", {})
                .get("attributes", {})
                .get("ohlcv_list", [])
            )

            if not page_data:
                break

            all_rows.extend(page_data)

            earliest_ts = min(int(row[0]) for row in page_data)
            if len(page_data) < 1000 or earliest_ts < cutoff_ts:
                break

            before_ts = earliest_ts - 1

        if not all_rows:
            return []

        results: list[PoolHistoryPoint] = []
        for row in all_rows:
            # row: [timestamp_s, open, high, low, close, volume]
            try:
                ts_s = int(row[0])
                if ts_s < cutoff_ts:
                    continue
                close_price = Decimal(str(row[4]))
                volume = Decimal(str(row[5]))

                if close_price <= Decimal("0"):
                    continue

                results.append(
                    PoolHistoryPoint(
                        pool_address=pool_address,
                        timestamp=ts_s,
                        price_token1_in_token0=close_price,
                        price_token0_in_token1=(
                            Decimal("1") / close_price
                        ),
                        volume_usd=volume,
                        tvl_usd=tvl_usd,
                        fee_growth_global_0=None,
                        fee_growth_global_1=None,
                        source="gecko_terminal",
                    )
                )
            except Exception as e:
                logger.warning(
                    "GeckoTerminalFetcher: skipping malformed row %s: %s", row, e
                )

        # Deduplicate by exact timestamp (keep last), sort ascending
        seen: dict[int, PoolHistoryPoint] = {}
        for entry in results:
            seen[entry.timestamp] = entry
        return sorted(seen.values(), key=lambda r: r.timestamp)

    def is_available(self) -> bool:
        """GeckoTerminal public API requires no key — always available."""
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_tvl(self, pool_address: str) -> Decimal:
        """Fetch current TVL from pool detail endpoint. Returns Decimal('0') on failure."""
        url = f"{_BASE}/networks/{self.network}/pools/{pool_address}"
        headers = {"User-Agent": "liquidity-bot-v2/1.0", "Accept": "application/json"}
        try:
            resp = self._get(url, headers, {})
            attr = resp.json().get("data", {}).get("attributes", {})
            raw = (
                attr.get("reserve_in_usd")
                or attr.get("liquidity_usd")
                or attr.get("tvl_usd")
            )
            if raw:
                return Decimal(str(raw))
        except Exception as e:
            logger.warning(
                "GeckoTerminalFetcher: TVL fetch failed for %s: %s", pool_address, e
            )
        return Decimal("0")

    def _get(
        self,
        url: str,
        headers: dict[str, str],
        params: dict,
    ) -> requests.Response:
        """Execute a GET with rate limiting and 429/5xx retry logic."""
        self._enforce_rate_limit()

        retries_429 = 0
        retries_5xx = 0

        while True:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.Timeout:
                raise FetchError(f"GeckoTerminal request timed out: {url}")
            except requests.ConnectionError as e:
                if retries_5xx < 3:
                    retries_5xx += 1
                    logger.warning(
                        "GeckoTerminal connection error (retry %d/3): %s", retries_5xx, e
                    )
                    time.sleep(10.0)
                    continue
                raise FetchError(f"GeckoTerminal connection error: {e}")

            if resp.status_code == 200:
                return resp

            if resp.status_code == 429:
                if retries_429 < len(_BACKOFFS):
                    retry_after_raw = resp.headers.get("Retry-After")
                    try:
                        retry_after_val = float(retry_after_raw) if retry_after_raw is not None else 0.0
                    except (ValueError, TypeError):
                        retry_after_val = 0.0
                    sleep_s = retry_after_val if retry_after_val > 1.0 else _BACKOFFS[retries_429]
                    retries_429 += 1
                    logger.warning(
                        "GeckoTerminal 429: sleeping %.1fs (attempt %d/5)",
                        sleep_s, retries_429
                    )
                    time.sleep(sleep_s)
                    continue
                raise FetchError("GeckoTerminal 429: all 5 retry attempts exhausted — giving up")

            if 500 <= resp.status_code < 600:
                if retries_5xx < 3:
                    retries_5xx += 1
                    logger.warning(
                        "GeckoTerminal %d: sleeping 10s (retry %d/3)",
                        resp.status_code, retries_5xx
                    )
                    time.sleep(10.0)
                    continue
                raise FetchError(
                    f"GeckoTerminal {resp.status_code} after 3 retries: {url}"
                )

            raise FetchError(
                f"GeckoTerminal HTTP {resp.status_code} for {url}: {resp.text[:200]}"
            )

    def _enforce_rate_limit(self) -> None:
        """Rolling-window rate limiter."""
        now = time.time()
        window = 60.0
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < window
        ]
        if len(self._request_timestamps) >= self.rate_limit_per_min - 2:
            raise RateLimitError(
                f"GeckoTerminal local rate limit reached ({self.rate_limit_per_min} req/min)"
            )
        self._request_timestamps.append(now)