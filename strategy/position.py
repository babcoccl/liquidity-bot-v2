"""
Position — snapshot of a liquidity position at entry time.
Immutable dataclass. No computation here.
"""
# AUDIT:status=complete
# AUDIT:sprint=11

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Position:
    pool_address: str           # lowercase hex
    pair_name: str              # e.g. "WETH-USDC"
    token0_symbol: str
    token1_symbol: str
    entry_timestamp: int        # UTC unix seconds
    entry_price_t1_in_t0: Decimal   # price_token1_in_token0 at entry
    entry_token0_price_usd: Decimal
    entry_token1_price_usd: Decimal
    entry_tvl_usd: Decimal
    tick_lower: int             # Uniswap v3 range lower tick
    tick_upper: int             # Uniswap v3 range upper tick
    liquidity_usd: Decimal      # USD value deposited