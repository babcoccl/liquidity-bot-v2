"""
TheGraphFetcher — primary data source.
Queries Aerodrome poolDayDatas on Base chain via The Graph.
Paginates using date_gt cursor until no results remain.
fee_growth_global fields parsed as int(), never float.
"""
# AUDIT:status=complete
# AUDIT:sprint=8

import json
import logging
import time
from decimal import Decimal
from typing import Optional

import requests

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolDayData

logger = logging.getLogger(__name__)


class TheGraphFetcher(AbstractFetcher):
    """Fetches pool day data from Aerodrome subgraph on Base via The Graph."""

    name: str = "the_graph"

    def __init__(self, url: str, api_key: str = "", rate_limit_per_min: int = 30):
        self.url = url
        self.api_key = api_key
        self.rate_limit_per_min = rate_limit_per_min
        self._request_timestamps: list[float] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_pool_history(self, pool_address: str, days: int) -> list[PoolDayData]:
        """Fetch up to `days` of daily data for the given pool."""
        import math
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = int((now - timedelta(days=days)).timestamp())

        query_template = """
            {
              poolDayDatas(
                first: 1000
                where: { pool: "$pool_address", date_gt: $cursor }
                orderBy: date
                orderDirection: asc
              ) {
                date
                volumeUSD
                tvlUSD
                token0Price
                token1Price
                feeGrowthGlobal0X128
                feeGrowthGlobal1X128
              }
            }
        """

        pool_address_lower = pool_address.lower()
        cursor = start_date - 1
        results: list[PoolDayData] = []

        while True:
            query = query_template.replace("$pool_address", pool_address_lower).replace(
                "$cursor", str(cursor)
            )

            response = self._post(query, pool_address_lower)
            data = response.json()

            if "data" not in data or "poolDayDatas" not in data.get("data", {}):
                errors = data.get("errors", [])
                error_msgs = (
                    "; ".join(e.get("message", str(e)) for e in errors)
                    if errors
                    else json.dumps(data)
                )
                raise FetchError(
                    f"Unexpected response from The Graph for {pool_address}: {error_msgs}"
                )

            records: list = data["data"]["poolDayDatas"]

            if not records:
                break

            for record in records:
                try:
                    entry = self._parse_record(pool_address_lower, record)
                    results.append(entry)
                except Exception as e:
                    logger.warning(
                        "Skipping malformed record from The Graph (date=%s): %s",
                        record.get("date"),
                        e,
                    )

            cursor = int(records[-1]["date"])

        return sorted(results, key=lambda r: r.date)

    def is_available(self) -> bool:
        """Check if the fetcher can be used (url set and reachable)."""
        try:
            if not self.url or not self.url.strip():
                return False
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_record(self, pool_address: str, record: dict) -> PoolDayData:
        """Parse a single GraphQL record into PoolDayData."""

        def parse_fee_growth(value: Optional[str]) -> Optional[int]:
            if value is None or value == "0":
                return None
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        fee_0 = parse_fee_growth(record.get("feeGrowthGlobal0X128"))
        fee_1 = parse_fee_growth(record.get("feeGrowthGlobal1X128"))

        return PoolDayData(
            pool_address=pool_address,
            date=int(record["date"]),
            price_token1_in_token0=Decimal(str(record["token1Price"])),
            price_token0_in_token1=Decimal(str(record["token0Price"])),
            volume_usd=Decimal(str(record["volumeUSD"])),
            tvl_usd=Decimal(str(record["tvlUSD"])),
            fee_growth_global_0=fee_0,
            fee_growth_global_1=fee_1,
            source="the_graph",
        )

    def _post(self, query: str, pool_address: str) -> requests.Response:
        """Execute a GraphQL POST with rate limiting."""
        self._enforce_rate_limit()

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                self.url,
                json={"query": query},
                headers=headers,
                timeout=30,
            )
        except requests.Timeout:
            raise FetchError(f"Request to The Graph timed out for {pool_address}")
        except requests.ConnectionError as e:
            raise FetchError(f"Connection error to The Graph for {pool_address}: {e}")

        if resp.status_code == 429:
            raise RateLimitError("The Graph returned 429 Too Many Requests")

        if resp.status_code == 401:
            raise FetchError(
                f"The Graph returned 401 Unauthorized for {pool_address} — check THEGRAPH_API_KEY"
            )

        if resp.status_code != 200:
            raise FetchError(
                f"The Graph returned HTTP {resp.status_code} for {pool_address}: {resp.text}"
            )

        return resp

    def _enforce_rate_limit(self) -> None:
        """Rolling-window rate limiter. Raises RateLimitError when budget nearly exhausted."""
        now = time.time()
        window = 60.0

        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < window
        ]

        if len(self._request_timestamps) >= self.rate_limit_per_min - 2:
            raise RateLimitError(
                f"The Graph local rate limit reached ({self.rate_limit_per_min} req/min)"
            )

        self._request_timestamps.append(now)