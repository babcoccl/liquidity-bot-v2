# AUDIT:status=complete
# AUDIT:sprint=1
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class PoolDayData:
    """
    Canonical daily data point for one pool.
    All data sources normalize into this structure before storage or use.
    fee_growth_global fields are stored as int (raw uint256), never float.
    Sources that cannot provide fee growth set those fields to None.
    """
    pool_address: str                        # lowercase hex
    date: int                                # Unix timestamp, start of day UTC
    price_token1_in_token0: Decimal          # token1Price from The Graph
    price_token0_in_token1: Decimal          # token0Price from The Graph
    volume_usd: Decimal
    tvl_usd: Decimal
    fee_growth_global_0: Optional[int]       # raw uint256; None if source cannot provide
    fee_growth_global_1: Optional[int]       # raw uint256; None if source cannot provide
    source: str                              # "the_graph" | "coingecko" | "defillama"