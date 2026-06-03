# AUDIT:status=complete
# AUDIT:sprint=9

from abc import ABC, abstractmethod
from typing import Any, List


class RateLimitError(Exception):
    """Source returned 429 or local rate budget exceeded."""


class FetchError(Exception):
    """Unrecoverable fetch failure: bad API key, malformed response, all sources exhausted."""


class AbstractFetcher(ABC):
    """
    Base class for all data source fetchers.
    Subclasses must set class attribute `name` to their source identifier.
    """
    name: str  # "the_graph" | "coingecko" | "defillama"

    @abstractmethod
    def fetch_pool_history(
        self,
        pool_address: str,
        days: int,
    ) -> List[Any]:
        """
        Fetch up to `days` of historical records for pool_address.

        Implementations may return PoolDayData (daily-bucketed) or
        PoolHistoryPoint (hourly-preserved) records. The router and
        loader layers handle both shapes via duck-typing.

        Must paginate internally — never truncate at source page size.
        Returns list sorted ascending by time field (date or timestamp).
        Raises RateLimitError if rate limited.
        Raises FetchError on unrecoverable error.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        Health-check the source.
        Returns False if source is known-down or API key is missing.
        Never raises — catches all exceptions and returns False.
        """
        ...