"""Single-pool backtest simulator for Uniswap V3-style concentrated liquidity."""
# AUDIT:status=partial
# AUDIT:sprint=1
# AUDIT:issue=All financial params use float instead of Decimal
# AUDIT:issue=Hardcoded defaults should come from config/default.yaml backtest section
# AUDIT:issue=PositionSimulator.step() raises NotImplementedError

from __future__ import annotations


class Position:
    """Represents an active LP position in a single pool."""

    def __init__(
        self,
        pool_id: str,
        entry_price: float,
        tick_lower: float,
        tick_upper: float,
        capital_usd: float,
        fee_rate: float = 0.0005,
    ):
        self.pool_id = pool_id
        self.entry_price = entry_price
        self.tick_lower = tick_lower
        self.tick_upper = tick_upper
        self.capital_usd = capital_usd
        self.fee_rate = fee_rate
        self.fees_earned_usd: float = 0.0
        self.current_value: float = capital_usd

    def update(
        self,
        current_price: float,
        volume_since_last: float,
    ) -> None:
        """Update position value based on new price and volume.

        Args:
            current_price:      Current token price.
            volume_since_last:  Trading volume since last update (USD).
        """
        from decimal import Decimal
        from core.il import compute_il_pct
        from core.fees import lp_fee_share

        # Compute IL percentage using new V3 API
        il_pct = compute_il_pct(
            entry_price=Decimal(str(self.entry_price)),
            current_price=Decimal(str(current_price)),
            price_lower=Decimal(str(self.tick_lower)),
            price_upper=Decimal(str(self.tick_upper)),
            capital_usd=Decimal(str(self.capital_usd)),
        )

        # Update position value (capital adjusted by IL)
        il_ratio = float(il_pct + Decimal("1"))
        self.current_value = self.capital_usd * il_ratio

        # Accumulate fees (simplified: proportional share of volume * fee_rate)
        fees = lp_fee_share(1.0, 1.0, volume_since_last * self.fee_rate)
        self.fees_earned_usd += fees
        self.current_value += fees


class PositionSimulator:
    """Stub simulator — raises NotImplementedError for step() per Sprint 1 spec."""

    def __init__(
        self,
        pool_id: str,
        tick_lower: float,
        tick_upper: float,
        initial_usd: float = 1000.0,
    ):
        self.pool_id = pool_id
        self.tick_lower = tick_lower
        self.tick_upper = tick_upper
        self.initial_usd = initial_usd

    def step(
        self,
        price: float,
        volume: float,
        fees_earned: float,
        timestamp: str,
    ) -> dict:
        raise NotImplementedError("Backtest simulator not implemented in Sprint 1")


class BacktestSimulator:
    """Simulates LP strategy on historical price data for a single pool."""

    def __init__(
        self,
        pool_id: str,
        initial_capital: float = 10000.0,
        tick_lower: float | None = None,
        tick_upper: float | None = None,
        fee_rate: float = 0.0005,
    ):
        self.pool_id = pool_id
        self.initial_capital = initial_capital
        self.tick_lower = tick_lower
        self.tick_upper = tick_upper
        self.fee_rate = fee_rate
        self.position: Position | None = None
        self.equity_curve: list[float] = [initial_capital]
        self.cash: float = initial_capital

    def enter(
        self,
        entry_price: float,
        capital: float | None = None,
    ) -> None:
        """Open a new LP position.

        Args:
            entry_price: Price at which the position is opened.
            capital:     Amount to deploy (default: all available cash).
        """
        if self.position is not None:
            return  # Already in a position

        amount = capital if capital is not None else self.cash
        if amount <= 0:
            return

        self.cash -= amount

        # Auto-set tick range if not provided
        tick_lower = self.tick_lower or (entry_price * 0.9)
        tick_upper = self.tick_upper or (entry_price * 1.1)

        self.position = Position(
            pool_id=self.pool_id,
            entry_price=entry_price,
            tick_lower=tick_lower,
            tick_upper=tick_upper,
            capital_usd=amount,
            fee_rate=self.fee_rate,
        )

    def exit(self) -> float:
        """Close the current position and return proceeds.

        Returns:
            USD amount received from exiting (0 if no position).
        """
        if self.position is None:
            return 0.0

        proceeds = self.position.current_value
        self.cash += proceeds
        self.position = None
        return proceeds

    def step(
        self,
        current_price: float,
        volume: float,
    ) -> float:
        """Advance the simulation by one time step.

        Args:
            current_price: Current token price at this step.
            volume:        Trading volume during this step (USD).

        Returns:
            Total portfolio value (cash + position value).
        """
        if self.position is not None:
            self.position.update(current_price, volume)
            total = self.cash + self.position.current_value
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
        total_fees = self.position.fees_earned_usd if self.position else 0.0

        # Compute IL loss
        il_loss = 0.0
        if self.position:
            from decimal import Decimal
            from core.il import compute_il
            il_result = compute_il(
                entry_price=Decimal(str(self.position.entry_price)),
                current_price=Decimal(str(self.position.current_value / self.position.capital_usd)) if self.position.capital_usd > 0 else Decimal("0"),
                price_lower=Decimal(str(self.position.tick_lower)),
                price_upper=Decimal(str(self.position.tick_upper)),
                capital_usd=Decimal(str(self.position.capital_usd)),
            )
            il_loss = float(il_result)

        return portfolio_summary(
            total_value=final_value,
            initial_capital=self.initial_capital,
            total_fees_earned=total_fees,
            total_il_loss=il_loss,
            equity_curve=self.equity_curve,
        )