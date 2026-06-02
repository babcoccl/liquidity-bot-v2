"""Base executor stub for live on-chain execution.

All methods raise NotImplementedError — live execution is not implemented in v2 yet.
Subclasses should implement actual chain interaction (e.g., via web3.py or ethers).
"""
# AUDIT:status=stub
# AUDIT:sprint=1
# AUDIT:issue=all methods raise NotImplementedError; no real implementation

from __future__ import annotations


class BaseExecutor:
    """Stub for live on-chain execution. All methods raise NotImplementedError."""

    def mint_position(self, pool: str, tick_lower: int, tick_upper: int, amount_usd: float) -> dict:
        """Mint a new concentrated liquidity position.

        Args:
            pool:        Pool address or identifier.
            tick_lower:  Lower tick boundary.
            tick_upper:  Upper tick boundary.
            amount_usd:  USD amount to deposit.

        Returns:
            Dict with transaction hash, nonce, and position details.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")

    def burn_position(self, position_id: int) -> dict:
        """Burn (remove) an existing liquidity position.

        Args:
            position_id: NFT token ID of the position to burn.

        Returns:
            Dict with transaction hash and withdrawn amounts.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")

    def harvest_fees(self, position_id: int) -> dict:
        """Harvest accumulated fees from a position without burning it.

        Args:
            position_id: NFT token ID of the position.

        Returns:
            Dict with transaction hash and harvested fee amounts.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")

    def get_position_state(self, position_id: int) -> dict:
        """Query the current on-chain state of a position.

        Args:
            position_id: NFT token ID to query.

        Returns:
            Dict with liquidity, fees owed, tick range, and other state.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")

    def increase_liquidity(self, position_id: int, amount_usd: float) -> dict:
        """Add more liquidity to an existing position.

        Args:
            position_id: NFT token ID of the position.
            amount_usd:  Additional USD to deposit.

        Returns:
            Dict with transaction hash and updated liquidity.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")

    def decrease_liquidity(self, position_id: int, amount_usd: float) -> dict:
        """Remove some liquidity from an existing position without burning it.

        Args:
            position_id: NFT token ID of the position.
            amount_usd:  USD amount to withdraw.

        Returns:
            Dict with transaction hash and withdrawn amounts.
        """
        raise NotImplementedError("Live execution not implemented in v2 yet")