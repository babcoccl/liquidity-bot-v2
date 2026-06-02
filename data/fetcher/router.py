"""
FetchRouter — orchestrates fallback chain across fetchers.
Tries fetchers in priority order.
Falls back on RateLimitError or empty result.
Raises FetchError on hard failure or when all sources exhausted.
"""

import logging

from data.fetcher.base import AbstractFetcher, FetchError, RateLimitError
from core.models import PoolDayData

logger = logging.getLogger(__name__)


class FetchRouter:
    """Routes fetch requests through a priority-ordered list of fetchers."""

    def __init__(self, fetchers: list[AbstractFetcher]):
        self.fetchers = fetchers

    def fetch(self, pool_address: str, days: int) -> list[PoolDayData]:
        """Fetch pool history, falling back through available sources."""
        for fetcher in self.fetchers:
            # Skip unavailable fetchers silently
            if not fetcher.is_available():
                continue

            try:
                result = fetcher.fetch_pool_history(pool_address, days)
            except RateLimitError:
                logger.warning(
                    "Rate limit hit on fetcher '%s', trying next source",
                    fetcher.name,
                )
                continue
            except FetchError:
                # Hard failure — do not fall back
                raise

            if not result:
                logger.warning(
                    "Fetcher '%s' returned empty result for %s, trying next source",
                    fetcher.name,
                    pool_address,
                )
                continue

            return result

        raise FetchError(f"All sources exhausted for {pool_address}")