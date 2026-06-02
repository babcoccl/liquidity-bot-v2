"""
PoolRegistry — loads, validates, and provides lookup for pool configurations.
Source of truth for all pool metadata in the codebase.
Backed by registry/registry.json.
"""
# AUDIT:status=complete
# AUDIT:sprint=4

from __future__ import annotations

import json
import logging
from pathlib import Path

from registry.types import PoolConfig, PriceReference, TokenConfig

logger = logging.getLogger(__name__)

_VALID_FEE_TIERS = {100, 500, 3000, 10000}


class PoolRegistry:
    """Loads and provides lookup for pool configurations from registry.json."""

    def __init__(self, path: Path = Path("registry/registry.json")):
        self.path = Path(path)
        self._pools: dict[str, PoolConfig] = {}

    def load(self) -> None:
        """Load pool configurations from registry.json."""
        if not self.path.exists():
            raise FileNotFoundError(f"Registry file not found: {self.path}")

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON in {self.path.name}: {e}")

        if not isinstance(data, list):
            raise ValueError("registry.json must be a JSON array")

        self._pools = {}
        for entry in data:
            pool_address = str(entry["pool_address"]).lower()

            token0 = TokenConfig(
                symbol=entry["token0"]["symbol"],
                address=str(entry["token0"]["address"]).lower(),
                decimals=int(entry["token0"]["decimals"]),
            )
            token1 = TokenConfig(
                symbol=entry["token1"]["symbol"],
                address=str(entry["token1"]["address"]).lower(),
                decimals=int(entry["token1"]["decimals"]),
            )

            price_reference = {
                symbol: PriceReference(
                    quote=ref["quote"],
                    source_pool=str(ref["source_pool"]).lower(),
                )
                for symbol, ref in entry.get("price_reference", {}).items()
            }

            pool = PoolConfig(
                pool_address=pool_address,
                pair_name=entry["pair_name"],
                token0=token0,
                token1=token1,
                fee_tier=int(entry["fee_tier"]),
                price_reference=price_reference,
            )
            self._pools[pool_address] = pool

        logger.info("PoolRegistry loaded %d pool(s) from %s", len(self._pools), self.path)

    def get(self, pool_address: str) -> PoolConfig:
        """Return PoolConfig for the given address. Case-insensitive."""
        key = pool_address.lower()
        if key not in self._pools:
            raise KeyError(f"Pool {pool_address} not in registry")
        return self._pools[key]

    def all(self) -> list[PoolConfig]:
        """Return all PoolConfigs sorted ascending by pair_name."""
        return sorted(self._pools.values(), key=lambda p: p.pair_name)

    def is_loaded(self) -> bool:
        """Return True if load() has been called and at least one pool was loaded."""
        return len(self._pools) > 0

    def validate(self) -> list[str]:
        """Validate all pools. Returns list of error strings. Empty list = clean."""
        errors: list[str] = []
        for pool in self._pools.values():
            if not pool.pool_address or not pool.pool_address.startswith("0x"):
                errors.append(
                    f"{pool.pair_name}: pool_address must be non-empty and start with '0x'"
                )
            if not (1 <= pool.token0.decimals <= 18):
                errors.append(
                    f"{pool.pair_name}: token0.decimals {pool.token0.decimals} out of range [1, 18]"
                )
            if not (1 <= pool.token1.decimals <= 18):
                errors.append(
                    f"{pool.pair_name}: token1.decimals {pool.token1.decimals} out of range [1, 18]"
                )
            if pool.fee_tier not in _VALID_FEE_TIERS:
                errors.append(
                    f"{pool.pair_name}: fee_tier {pool.fee_tier} not in {_VALID_FEE_TIERS}"
                )
            if not pool.pair_name:
                errors.append(f"{pool.pool_address}: pair_name is empty")
            for symbol, ref in pool.price_reference.items():
                if not ref.source_pool.startswith("0x"):
                    errors.append(
                        f"{pool.pair_name}: price_reference[{symbol}].source_pool must start with '0x'"
                    )
        return errors