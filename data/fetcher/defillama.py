"""
DeFiLlamaFetcher — fallback source 2.
Provides TVL history via api.llama.fi.
fee_growth_global fields always None.
price fields set to Decimal("0") — DeFiLlama does not provide token price candles.
No API key required.
"""
# AUDIT:status=complete
# AUDIT:sprint=1

import logging
import time
from decimal import Decimal
from typing import Any

import requests

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolDayData

logger = logging.getLogger(__name__)


class DeFiLlamaFetcher(AbstractFetcher):
    """Fetches TVL history via DeFiLlama API."""

    name: str = "defillama"

    BASE_URL = "https://api.llama.fi"

    def __init__(self, protocol_slug: str, rate_limit_per_min: int = 100):
        self.protocol_slug = protocol_slug
        self.rate_limit_per_min = rate_limit_per_min
        self._request_timestamps: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_pool_history(self, pool_address: str, days: int) -> list[PoolDayData]:
        """Fetch TVL history for the configured protocol."""
        url = f"{self.BASE_URL}/protocol/{self.protocol_slug}"

        resp = self._get(url)
        data: dict[str, Any] = resp.json()

        tvl_array: list[dict[str, Any]] = data.get("tvl", [])

        # Filter to last `days` entries only
        if len(tvl_array) > days:
            tvl_array = tvl_array[-days:]

        results: list[PoolDayData] = []
        for entry in tvl_array:
            ts = int(entry.get("date", 0))
            total_liquidity = entry.get("totalLiquidityUSD", 0.0)

            record = PoolDayData(
                pool_address=pool_address.lower(),
                date=ts,
                price_token1_in_token0=Decimal("0"),
                price_token0_in_token1=Decimal("0"),
                volume_usd=Decimal("0"),
                tvl_usd=Decimal(str(total_liquidity)),
                fee_growth_global_0=None,
                fee_growth_global_1=None,
                source="defillama",
            )
            results.append(record)

        return sorted(results, key=lambda r: r.date)

    def is_available(self) -> bool:
        """Check if DeFiLlama API is reachable."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/protocols",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get(self, url: str) -> requests.Response:
        """Execute a GET request with rate limiting."""
        self._enforce_rate_limit()

        try:
            resp = requests.get(url, timeout=30)
        except requests.Timeout as e:
            raise FetchError(f"DeFiLlama request timed out: {e}")
        except requests.ConnectionError as e:
            raise FetchError(f"Connection error to DeFiLlama: {e}")

        if resp.status_code == 429:
            raise RateLimitError("DeFiLlama returned 429 Too Many Requests")

        if resp.status_code != 200:
            raise FetchError(
                f"DeFiLlama returned HTTP {resp.status_code}: {resp.text}"
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
                f"DeFiLlama local rate limit reached ({self.rate_limit_per_min} req/min)"
            )

        self._request_timestamps.append(now)