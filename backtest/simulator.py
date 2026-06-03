"""Single-pool backtest simulator for Uniswap V3-style concentrated liquidity.
All financial values use TaggedDecimal — never float or bare Decimal.
PositionSimulator.step() is now fully implemented.
"""
# AUDIT:status=complete
# AUDIT:sprint=7

from __future__ import annotations
from decimal import Decimal

from core.units import (
    TaggedDecimal,
    DenominationError,
    usd,
    bps,
    price_t1_t0,
    ratio,
)
from core.models import PoolDayData


class Position:
    """Represents an active LP position in a single pool. All values TaggedDecimal."""

    def __init__(
        self,
        pool_id: str,
        entry_price: TaggedDecimal,       # PRICE_T1_T0
        price_lower: TaggedDecimal,       # PRICE_T1_T0
        price_upper: TaggedDecimal,       # PRICE_T1_T0
        capital_usd: TaggedDecimal,       # USD
        fee_tier_bps: TaggedDecimal,      # BPS
    ) -> None:
        self.pool_id = pool_id
        self.entry_price = entry_price
        self.price_lower = price_lower
        self.price_upper = price_upper
        self.capital_usd = capital_usd
        self.fee_tier_bps = fee_tier_bps
        self.fees_earned_usd: TaggedDecimal = usd("0")
        self.current_value_usd: TaggedDecimal = capital_usd
        self.last_price: TaggedDecimal = entry_price   # updated each step; used by summary()

    def update(
        self,
        current_price: TaggedDecimal,    # PRICE_T1_T0
        volume_usd: TaggedDecimal,       # USD
        pool_tvl_usd: TaggedDecimal,     # USD
    ) -> None:
        """
        Update position value and accumulate fees for one time step.
        Uses core.il.compute_il for V3 IL math.
        Uses core.fees.lp_fee_share for fee attribution.
        """
        from core.il import compute_il
        from core.fees import lp_fee_share, estimate_daily_fees

        # IL computation — all Decimal, core.il unchanged
        il_usd = compute_il(
            entry_price=self.entry_price.value,
            current_price=current_price.value,
            price_lower=self.price_lower.value,
            price_upper=self.price_upper.value,
            capital_usd=self.capital_usd.value,
        )

        # Position value = initial capital adjusted by IL
        self.current_value_usd = usd(self.capital_usd.value + il_usd)
        self.last_price = current_price   # record last seen price for summary()

        # Fee attribution: estimate pool daily fees, then take LP share
        daily_fees = estimate_daily_fees(pool_tvl_usd, volume_usd, self.fee_tier_bps)
        step_fees = lp_fee_share(self.current_value_usd, pool_tvl_usd, daily_fees)

        self.fees_earned_usd = self.fees_earned_usd + step_fees
        self.current_value_usd = self.current_value_usd + step_fees


class PositionSimulator:
    """
    Per-pool simulator used by BacktestHarness.
    Accepts PoolDayData records via step().
    """

    def __init__(
        self,
        pool_id: str,
        price_lower_multiplier: Decimal = Decimal("0.9"),
        price_upper_multiplier: Decimal = Decimal("1.1"),
        initial_usd: TaggedDecimal | None = None,
        fee_tier_bps: TaggedDecimal | None = None,
    ) -> None:
        self.pool_id = pool_id
        self.price_lower_multiplier = price_lower_multiplier
        self.price_upper_multiplier = price_upper_multiplier
        self.initial_usd = initial_usd or usd("10000")
        self.fee_tier_bps = fee_tier_bps or bps("30")
        self.position: Position | None = None
        self.cash: TaggedDecimal = self.initial_usd
        self.equity_curve: list[TaggedDecimal] = [self.initial_usd]

    def step(self, record: "PoolDayData") -> TaggedDecimal:
        """
        Advance simulation by one day using a PoolDayData record.
        Opens position on first step using record price ± multipliers.
        Returns total portfolio value (USD) after this step.
        """
        current_price = price_t1_t0(record.price_token1_in_token0)
        volume = usd(record.volume_usd)
        tvl = usd(record.tvl_usd) if record.tvl_usd > Decimal("0") else usd(self.initial_usd.value)

        if self.position is None:
            # Enter position on first step
            lower = price_t1_t0(current_price.value * self.price_lower_multiplier)
            upper = price_t1_t0(current_price.value * self.price_upper_multiplier)
            self.position = Position(
                pool_id=self.pool_id,
                entry_price=current_price,
                price_lower=lower,
                price_upper=upper,
                capital_usd=self.cash,
                fee_tier_bps=self.fee_tier_bps,
            )
            self.cash = usd("0")

        self.position.update(current_price, volume, tvl)
        total = self.cash + self.position.current_value_usd
        self.equity_curve.append(total)
        return total


class BacktestSimulator:
    """Simulates LP strategy on historical price data for a single pool."""

    def __init__(
        self,
        pool_id: str,
        initial_capital: TaggedDecimal | None = None,
        tick_lower_multiplier: Decimal | None = None,
        tick_upper_multiplier: Decimal | None = None,
        fee_tier_bps: TaggedDecimal | None = None,
    ):
        self.pool_id = pool_id
        self.initial_capital = initial_capital or usd("10000")
        self.tick_lower_multiplier = tick_lower_multiplier or Decimal("0.9")
        self.tick_upper_multiplier = tick_upper_multiplier or Decimal("1.1")
        self.fee_tier_bps = fee_tier_bps or bps("30")
        self.position: Position | None = None
        self.equity_curve: list[TaggedDecimal] = [self.initial_capital]
        self.cash: TaggedDecimal = self.initial_capital

    def enter(
        self,
        entry_price: TaggedDecimal,  # PRICE_T1_T0
        capital: TaggedDecimal | None = None,
    ) -> None:
        """Open a new LP position.

        Args:
            entry_price: Price at which the position is opened (PRICE_T1_T0).
            capital:     Amount to deploy (default: all available cash).
        """
        if self.position is not None:
            return  # Already in a position

        amount = capital if capital is not None else self.cash
        if amount.value <= 0:
            return

        self.cash = usd(self.cash.value - amount.value)

        # Auto-set price range if not provided
        tick_lower = price_t1_t0(entry_price.value * self.tick_lower_multiplier)
        tick_upper = price_t1_t0(entry_price.value * self.tick_upper_multiplier)

        self.position = Position(
            pool_id=self.pool_id,
            entry_price=entry_price,
            price_lower=tick_lower,
            price_upper=tick_upper,
            capital_usd=amount,
            fee_tier_bps=self.fee_tier_bps,
        )

    def exit(self) -> TaggedDecimal:
        """Close the current position and return proceeds.

        Returns:
            USD amount received from exiting (0 if no position).
        """
        if self.position is None:
            return usd("0")

        proceeds = self.position.current_value_usd
        self.cash = usd(self.cash.value + proceeds.value)
        self.position = None
        return proceeds

    def step(
        self,
        current_price: TaggedDecimal,  # PRICE_T1_T0
        volume: TaggedDecimal,         # USD
        pool_tvl_usd: TaggedDecimal | None = None,  # USD
    ) -> TaggedDecimal:
        """Advance the simulation by one time step.

        Args:
            current_price: Current token price at this step (PRICE_T1_T0).
            volume:        Trading volume during this step (USD).
            pool_tvl_usd:  Pool TVL (USD). Defaults to initial_capital if not provided.

        Returns:
            Total portfolio value (cash + position value) as USD.
        """
        tvl = pool_tvl_usd or self.initial_capital

        if self.position is not None:
            self.position.update(current_price, volume, tvl)
            total = usd(self.cash.value + self.position.current_value_usd.value)
        else:
            total = self.cash

        self.equity_curve.append(total)
        return total

    def summary(self) -> dict:
        """Generate a summary of the backtest run.

        Returns:
            Dict with final value, PnL, fees earned, etc.
        """
        from core.metrics import portfolio_summary, max_drawdown

        final_value = self.equity_curve[-1] if self.equity_curve else self.initial_capital
        total_fees = self.position.fees_earned_usd if self.position else usd("0")

        # Compute IL loss
        il_loss = Decimal("0")
        if self.position:
            from core.il import compute_il
            il_loss = compute_il(
                entry_price=self.position.entry_price.value,
                current_price=self.position.last_price.value,
                price_lower=self.position.price_lower.value,
                price_upper=self.position.price_upper.value,
                capital_usd=self.position.capital_usd.value,
            )

        # BOUNDARY: metrics.py uses float — pass .value here intentionally
        return portfolio_summary(
            total_value=float(final_value.value),
            initial_capital=float(self.initial_capital.value),
            total_fees_earned=float(total_fees.value),
            total_il_loss=float(il_loss),
            equity_curve=[float(v.value) for v in self.equity_curve],
        )