from abc import ABC, abstractmethod
from core.models import PoolDayData


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
    ) -> list[PoolDayData]:
        """
        Fetch up to `days` of daily data for pool_address.
        Must paginate internally — never truncate at source page size.
        Returns list sorted ascending by date.
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