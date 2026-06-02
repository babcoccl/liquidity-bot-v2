"""Multi-pool backtesting engine with capital rotation."""
# AUDIT:status=partial
# AUDIT:sprint=1
# AUDIT:issue=All financial params use float instead of Decimal
# AUDIT:issue=Hardcoded defaults should come from config/default.yaml backtest section

from __future__ import annotations

import pandas as pd


class MultiPoolBacktest:
    """Manages backtesting across multiple pools with rotation logic."""

    def __init__(
        self,
        pool_ids: list[str],
        initial_capital: float = 10000.0,
        min_entry_score: float = 0.25,
        rebalance_cooldown_hours: float = 4.0,
        max_rebalances_per_pool_per_day: int = 3,
    ):
        self.pool_ids = pool_ids
        self.initial_capital = initial_capital
        self.min_entry_score = min_entry_score
        self.rebalance_cooldown_hours = rebalance_cooldown_hours
        self.max_rebalances_per_pool_per_day = max_rebalances_per_pool_per_day

        # State tracking
        self.cash: float = initial_capital
        self.active_positions: dict[str, dict] = {}  # pool_id -> position info
        self.rebalance_count: dict[str, int] = {pid: 0 for pid in pool_ids}
        self.last_rebalance_time: dict[str, float] = {pid: -999.0 for pid in pool_ids}
        self.equity_curve: list[float] = [initial_capital]

    def total_value(self) -> float:
        """Calculate total portfolio value (cash + all positions)."""
        position_value = sum(
            info.get("current_value", 0.0) for info in self.active_positions.values()
        )
        return self.cash + position_value

    def can_rebalance(self, pool_id: str, current_time: float) -> bool:
        """Check if a pool can be rebalanced based on cooldown and daily limits.

        Args:
            pool_id:      Pool identifier.
            current_time: Current simulation time (hours from start).

        Returns:
            True if rebalance is allowed.
        """
        # Check cooldown
        last_time = self.last_rebalance_time.get(pool_id, -999.0)
        if current_time - last_time < self.rebalance_cooldown_hours:
            return False

        # Check daily limit (simplified: count / max * 24 hours window)
        day_index = int(current_time // 24)
        # In a full implementation, track per-day counts
        return True

    def evaluate_entry(
        self,
        pool_scores: dict[str, float],
        current_prices: dict[str, float],
        current_time: float,
    ) -> list[tuple[str, float]]:
        """Determine which pools to enter based on scores.

        Args:
            pool_scores:     Dict of pool_id -> composite score.
            current_prices:  Dict of pool_id -> current price.
            current_time:    Current simulation time (hours).

        Returns:
            List of (pool_id, capital) tuples to enter.
        """
        entries: list[tuple[str, float]] = []

        for pool_id in self.pool_ids:
            score = pool_scores.get(pool_id, 0.0)

            # Skip if below minimum entry score
            if score < self.min_entry_score:
                continue

            # Skip if already in position
            if pool_id in self.active_positions:
                continue

            # Check rebalance constraints
            if not self.can_rebalance(pool_id, current_time):
                continue

            # Allocate capital (equal weight for now)
            allocation = self.cash / max(1, len(self.pool_ids))
            if allocation > 0:
                entries.append((pool_id, allocation))

        return entries

    def evaluate_exit(
        self,
        exit_signals: dict[str, list[str]],
        current_prices: dict[str, float],
    ) -> list[str]:
        """Determine which pools to exit based on signals.

        Args:
            exit_signals:   Dict of pool_id -> list of triggered signal names.
            current_prices: Dict of pool_id -> current price.

        Returns:
            List of pool_ids to exit.
        """
        exits: list[str] = []

        for pool_id, signals in exit_signals.items():
            if len(signals) > 0 and pool_id in self.active_positions:
                exits.append(pool_id)

        return exits

    def step(
        self,
        timestamp: float,
        prices: dict[str, float],
        volumes: dict[str, float],
        scores: dict[str, float] | None = None,
        exit_signals: dict[str, list[str]] | None = None,
    ) -> float:
        """Advance the multi-pool backtest by one time step.

        Args:
            timestamp:     Current time in hours from start.
            prices:        Dict of pool_id -> current price.
            volumes:       Dict of pool_id -> volume since last step.
            scores:        Optional dict of pool_id -> composite score.
            exit_signals:  Optional dict of pool_id -> triggered signals.

        Returns:
            Total portfolio value after this step.
        """
        # Update existing positions
        for pool_id, info in list(self.active_positions.items()):
            price = prices.get(pool_id, 0)
            volume = volumes.get(pool_id, 0)

            if "simulator" in info:
                info["simulator"].step(price, volume)
                # Update tracked value
                info["current_value"] = info["simulator"].position.current_value if info["simulator"].position else 0.0

        # Evaluate exits
        if exit_signals:
            pools_to_exit = self.evaluate_exit(exit_signals, prices)
            for pool_id in pools_to_exit:
                if pool_id in self.active_positions:
                    info = self.active_positions[pool_id]
                    if "simulator" in info:
                        proceeds = info["simulator"].exit()
                        self.cash += proceeds
                    del self.active_positions[pool_id]

        # Evaluate entries
        if scores:
            entries = self.evaluate_entry(scores, prices, timestamp)
            for pool_id, capital in entries:
                price = prices.get(pool_id, 0)
                if price > 0 and capital > 0:
                    from backtest.simulator import BacktestSimulator

                    sim = BacktestSimulator(
                        pool_id=pool_id,
                        initial_capital=capital,
                    )
                    sim.enter(price, capital)
                    self.active_positions[pool_id] = {
                        "simulator": sim,
                        "current_value": capital,
                        "entry_time": timestamp,
                    }
                    self.cash -= capital
                    self.rebalance_count[pool_id] = self.rebalance_count.get(pool_id, 0) + 1
                    self.last_rebalance_time[pool_id] = timestamp

        # Record equity
        total = self.total_value()
        self.equity_curve.append(total)
        return total

    def summary(self) -> dict:
        """Generate a final summary of the multi-pool backtest.

        Returns:
            Dict with portfolio-level metrics.
        """
        from core.metrics import portfolio_summary, max_drawdown

        final_value = self.equity_curve[-1] if self.equity_curve else self.initial_capital

        return {
            "final_value": round(final_value, 2),
            "initial_capital": self.initial_capital,
            "total_pnl": round(final_value - self.initial_capital, 2),
            "pnl_pct": round((final_value / self.initial_capital - 1) * 100, 2),
            "max_drawdown": round(max_drawdown(self.equity_curve), 4),
            "active_positions_at_end": len(self.active_positions),
        }

    def equity_df(self) -> pd.DataFrame:
        """Return the equity curve as a pandas DataFrame.

        Returns:
            DataFrame with 'step' and 'value' columns.
        """
        return pd.DataFrame({
            "step": range(len(self.equity_curve)),
            "value": self.equity_curve,
        })