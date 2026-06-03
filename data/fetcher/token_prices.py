"""
TokenPriceFetcher — token-level historical price source.
Fetches hourly-ish token USD price history from CoinGecko.
Normalizes to TokenHistoryPoint records for trend/exit signals.
"""
# AUDIT:status=complete
# AUDIT:sprint=9-hotfix2

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import requests

from data.fetcher.base import FetchError, RateLimitError
from core.models import TokenHistoryPoint

logger = logging.getLogger(__name__)


class TokenPriceFetcher:
    """Fetches token market data via CoinGecko API for trend detection."""

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
        self._registry_cache: Optional[dict[str, dict]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_token_history(
        self,
        token_symbol: str,
        token_address: str,
        days: int,
    ) -> list[TokenHistoryPoint]:
        """
        Fetch hourly-ish USD price history for a token from CoinGecko.

        Args:
            token_symbol: e.g. "WETH", "USDC" — used to resolve coin_id
            token_address: lowercase hex address stored on output records
            days: lookback window in days

        Returns:
            Sorted list of TokenHistoryPoint records (ascending by timestamp).
        """
        coin_id = self.COIN_ID_MAP.get(token_symbol)
        if coin_id is None:
            raise FetchError(
                f"TokenPriceFetcher: no coin_id mapping for {token_symbol}. "
                f"Add to COIN_ID_MAP."
            )

        token_address = token_address.lower().strip()

        url = f"{self.BASE_URL}/coins/{coin_id}/market_chart"

        params: dict[str, Any] = {
            "vs_currency": "usd",
            "days": days,
            "interval": "hourly",
        }

        headers: dict[str, str] = {"Accept": "application/json"}
        if self.api_key:
            headers["x-cg-pro-api-key"] = self.api_key

        resp = self._get(url, headers, params)
        data: dict[str, Any] = resp.json()

        prices_raw: list[list] = data.get("prices", [])
        volumes_raw: list[list] = data.get("total_volumes", [])
        market_caps_raw: list[list] = data.get("market_caps", [])

        if not prices_raw:
            return []

        # Build lookup maps by raw timestamp
        volume_map: dict[int, float] = {}
        for entry in volumes_raw:
            ts = int(entry[0])
            volume_map[ts] = entry[1]

        mcap_map: dict[int, float] = {}
        for entry in market_caps_raw:
            ts = int(entry[0])
            mcap_map[ts] = entry[1]

        results: list[TokenHistoryPoint] = []
        for price_entry in prices_raw:
            timestamp_ms: int = int(price_entry[0])
            price_usd_val: float = price_entry[1]

            # Normalize to exact UTC hour bucket (seconds)
            timestamp = (timestamp_ms // 3600000) * 3600

            volume_usd_val = volume_map.get(timestamp_ms, 0.0)
            mcap_usd_val = mcap_map.get(timestamp_ms, None)

            if price_usd_val <= 0:
                continue

            results.append(
                TokenHistoryPoint(
                    token_address=token_address,
                    symbol=token_symbol,
                    timestamp=timestamp,
                    price_usd=Decimal(str(price_usd_val)),
                    volume_usd=Decimal(str(volume_usd_val)),
                    market_cap_usd=Decimal(str(mcap_usd_val)) if mcap_usd_val is not None else None,
                    source="coingecko",
                )
            )

        # Dedup by timestamp (keep last), sort ascending
        seen: dict[int, TokenHistoryPoint] = {}
        for entry in results:
            seen[entry.timestamp] = entry
        return sorted(seen.values(), key=lambda r: r.timestamp)

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

    def _get(
        self,
        url: str,
        headers: dict[str, str],
        params: Optional[dict] = None,
    ) -> requests.Response:
        """Execute a GET request with rate limiting and retry logic."""
        self._enforce_rate_limit()

        retries_429 = 0
        backoffs = [15, 30, 60]

        while True:
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.Timeout as e:
                raise FetchError(f"CoinGecko request timed out: {e}")
            except requests.ConnectionError as e:
                raise FetchError(f"Connection error to CoinGecko: {e}")

            if resp.status_code == 200:
                return resp

            if resp.status_code == 429:
                if retries_429 < len(backoffs):
                    retry_after_raw = resp.headers.get("Retry-After")
                    try:
                        retry_after_val = float(retry_after_raw) if retry_after_raw is not None else 0.0
                    except (ValueError, TypeError):
                        retry_after_val = 0.0
                    sleep_s = retry_after_val if retry_after_val > 1.0 else backoffs[retries_429]
                    retries_429 += 1
                    logger.warning(
                        "TokenPriceFetcher 429: sleeping %.1fs (attempt %d)",
                        sleep_s, retries_429,
                    )
                    time.sleep(sleep_s)
                    continue
                raise RateLimitError("CoinGecko returned 429 Too Many Requests")

            if resp.status_code == 404:
                raise FetchError(
                    f"CoinGecko returned 404 for {url} — coin_id may be incorrect"
                )

            raise FetchError(
                f"CoinGecko returned HTTP {resp.status_code}: {resp.text[:300]}"
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
                f"TokenPriceFetcher local rate limit reached "
                f"({self.rate_limit_per_min} req/min)"
            )

        self._request_timestamps.append(now)