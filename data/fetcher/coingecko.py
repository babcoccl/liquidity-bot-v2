"""
CoinGeckoFetcher — fallback source 1.
Provides price candles and volume via CoinGecko market_chart API.
fee_growth_global fields always None (source cannot provide).
tvl_usd always Decimal("0") (source cannot provide).
"""
# AUDIT:status=complete
# AUDIT:sprint=9-hotfix2

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolDayData, PoolHistoryPoint

logger = logging.getLogger(__name__)


class CoinGeckoFetcher(AbstractFetcher):
    """Fetches token market data via CoinGecko API."""

    name: str = "coingecko"

    BASE_URL = "https://api.coingecko.com/api/v3"

    COIN_ID_MAP: dict[str, str] = {
        "WETH":    "weth",
        "ETH":     "ethereum",
        "USDC":    "usd-coin",
        "USDT":    "tether",
        "cbBTC":   "coinbase-wrapped-btc",
        "cbETH":   "coinbase-wrapped-staked-eth",
        "AERO":    "aerodrome-finance",
        "BRETT":   "based-brett",
        "VIRTUAL": "virtual-protocol",
        "MORPHO":  "morpho",
        "EURC":    "euro-coin",
        "eUSD":    "electronic-usd",
        "VVV":     "venice-token",
        "FAI":     "frax-ai",
        "KTA":     "kta",
    }

    def __init__(
        self,
        api_key: str = "",
        rate_limit_per_min: int = 30,
        registry_path: Path = Path("registry/registry.json"),
    ):
        self.api_key = api_key
        self.rate_limit_per_min = rate_limit_per_min
        self.registry_path = registry_path
        self._request_timestamps: list[float] = []
        self._registry_cache: dict[str, dict] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_pool_history(self, pool_address: str, days: int) -> list[PoolHistoryPoint]:
        """
        Fetch pool history using CoinGecko market_chart for the pool's token1.

        Returns synthesized hourly PoolHistoryPoint records expanded from
        daily source data (24 records per day, volume divided by 24).

        Resolves pool_address → token symbols via registry.
        Maps token1 symbol → CoinGecko coin_id via COIN_ID_MAP.
        Falls back to token0 if token1 not in COIN_ID_MAP.
        Re-stamps pool_address on all returned records.
        Raises FetchError if pool not in registry or no coin_id mapping found.
        """
        pool = self._load_registry_pool(pool_address)
        if pool is None:
            raise FetchError(
                f"CoinGeckoFetcher: pool {pool_address} not found in registry "
                f"at {self.registry_path}"
            )

        token1_symbol: str = pool["token1"]["symbol"]
        token0_symbol: str = pool["token0"]["symbol"]

        coin_id = self.COIN_ID_MAP.get(token1_symbol) or self.COIN_ID_MAP.get(token0_symbol)
        if coin_id is None:
            raise FetchError(
                f"CoinGeckoFetcher: no coin_id mapping for {token1_symbol} or "
                f"{token0_symbol} (pool {pool_address}). Add to COIN_ID_MAP."
            )

        daily_records = self.fetch_token_history(coin_id, days)

        hourly: list[PoolHistoryPoint] = []
        for day in daily_records:
            day_start = day.date
            hourly_volume = day.volume_usd / Decimal("24")
            for h in range(24):
                hourly.append(
                    PoolHistoryPoint(
                        pool_address=pool_address.lower(),
                        timestamp=day_start + h * 3600,
                        price_token1_in_token0=day.price_token1_in_token0,
                        price_token0_in_token1=day.price_token0_in_token1,
                        volume_usd=hourly_volume,
                        tvl_usd=day.tvl_usd,
                        fee_growth_global_0=None,
                        fee_growth_global_1=None,
                        source="coingecko",
                    )
                )
        return sorted(hourly, key=lambda r: r.timestamp)

    def _load_registry_pool(self, pool_address: str) -> dict | None:
        """
        Load pool entry from registry JSON by pool_address.
        Caches full registry on first call.
        Returns matching pool dict or None if not found.
        """
        if self._registry_cache is None:
            try:
                with open(self.registry_path, "r") as f:
                    pools: list[dict] = json.load(f)
                self._registry_cache = {
                    p["pool_address"].lower(): p for p in pools
                }
            except (FileNotFoundError, KeyError, json.JSONDecodeError) as e:
                logger.warning(
                    "CoinGeckoFetcher: could not load registry from %s: %s",
                    self.registry_path, e
                )
                self._registry_cache = {}

        return self._registry_cache.get(pool_address.lower())

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