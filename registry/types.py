"""
Registry type definitions.
PoolConfig and TokenConfig are frozen dataclasses.
All pool and token metadata used across the codebase flows through these types.
"""
# AUDIT:status=complete
# AUDIT:sprint=4

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class TokenConfig:
    symbol: str      # e.g. "USDC"
    address: str     # lowercase hex
    decimals: int    # e.g. 6 for USDC, 18 for ETH


@dataclass(frozen=True)
class PriceReference:
    quote: str         # symbol of the quote token, e.g. "USD"
    source_pool: str   # lowercase hex address of pool used for price resolution


@dataclass(frozen=True)
class PoolConfig:
    pool_address: str                            # lowercase hex
    pair_name: str                               # e.g. "USDC-ETH"
    token0: TokenConfig
    token1: TokenConfig
    fee_tier: int                                # basis points: 100, 500, 3000, 10000
    price_reference: dict[str, PriceReference]  # symbol -> PriceReference