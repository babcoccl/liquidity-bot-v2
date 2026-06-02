"""
CoinGeckoFetcher — fallback source 1.
Provides price candles and volume via CoinGecko market_chart API.
fee_growth_global fields always None (source cannot provide).
tvl_usd always Decimal("0") (source cannot provide).
"""

import logging
import time
from decimal import Decimal
from typing import Any

import requests

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolDayData

logger = logging.getLogger(__name__)


class CoinGeckoFetcher(AbstractFetcher):
    """Fetches token market data via CoinGecko API."""

    name: str = "coingecko"

    BASE_URL = "https://api.coingecko.com/api/v3"

    def __init__(self, api_key: str = "", rate_limit_per_min: int = 30):
        self.api_key = api_key
        self.rate_limit_per_min = rate_limit_per_min
        self._request_timestamps: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_pool_history(self, pool_address: str, days: int) -> list[PoolDayData]:
        """CoinGecko does not support pool addresses."""
        raise FetchError(
            "CoinGecko requires token_id, not pool_address. Use fetch_token_history() instead."
        )

    def fetch_token_history(self, token_id: str, days: int) -> list[PoolDayData]:
        """Fetch token market chart data and normalize to PoolDayData."""
        url = (
            f"{self.BASE_URL}/coins/{token_id}/market_chart"
            f"?vs_currency=usd&days={days}&interval=daily"
        )

        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        resp = self._get(url, headers)
        data: dict[str, Any] = resp.json()

        prices_raw: list[list] = data.get("prices", [])
        volumes_raw: list[list] = data.get("total_volumes", [])

        if not prices_raw:
            return []

        # Build lookup for volumes by timestamp
        volume_map: dict[int, float] = {}
        for entry in volumes_raw:
            ts = int(entry[0])
            volume_map[ts] = entry[1]

        results: list[PoolDayData] = []
        for price_entry in prices_raw:
            timestamp_ms: int = int(price_entry[0])
            price_usd: float = price_entry[1]

            # Round to UTC midnight
            date = (timestamp_ms // 86400000) * 86400

            volume_usd_val = volume_map.get(timestamp_ms, 0.0)

            if price_usd > 0:
                price_t1_in_t0 = Decimal(str(price_usd))
                price_t0_in_t1 = Decimal("1") / Decimal(str(price_usd))
            else:
                price_t1_in_t0 = Decimal("0")
                price_t0_in_t1 = Decimal("0")

            entry = PoolDayData(
                pool_address=token_id,
                date=date,
                price_token1_in_token0=price_t1_in_t0,
                price_token0_in_token1=price_t0_in_t1,
                volume_usd=Decimal(str(volume_usd_val)),
                tvl_usd=Decimal("0"),
                fee_growth_global_0=None,
                fee_growth_global_1=None,
                source="coingecko",
            )
            results.append(entry)

        return sorted(results, key=lambda r: r.date)

    def is_available(self) -> bool:
        """Check if CoinGecko API is reachable."""
        try:
            resp = requests.head(
                f"{self.BASE_URL}/ping",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, url: str, headers: dict[str, str]) -> requests.Response:
        """Execute a GET request with rate limiting."""
        self._enforce_rate_limit()

        try:
            resp = requests.get(url, headers=headers, timeout=30)
        except requests.Timeout as e:
            raise FetchError(f"CoinGecko request timed out: {e}")
        except requests.ConnectionError as e:
            raise FetchError(f"Connection error to CoinGecko: {e}")

        if resp.status_code == 429:
            raise RateLimitError("CoinGecko returned 429 Too Many Requests")

        if resp.status_code != 200:
            raise FetchError(
                f"CoinGecko returned HTTP {resp.status_code}: {resp.text}"
            )

        return resp

    def _enforce_rate_limit(self) -> None:
        """Rolling-window rate limiter."""
        now = time.time()
        window = 60.0

        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < window
        ]

        if len(self._request_timestamps) >= self.rate_limit_per_min - 2:
            raise RateLimitError(
                f"CoinGecko local rate limit reached ({self.rate_limit_per_min} req/min)"
            )

        self._request_timestamps.append(now)