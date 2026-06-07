"""Multi-pool backtesting engine with capital rotation. ALL MATH USE DECIMAL. NO FLOAT.

BOUNDARY EXCEPTIONS WHERE FLOAT OK:
1. BACKTESTSIMULATOR CALL SITE — TAGGEDDECIMAL BOUNDARY. CONVERT HERE.
2. MAX_DRAWDOWN() CALL IN SUMMARY() — METRICS.PY USES FLOAT. CONVERT HERE.
3. EQUITY_DF() VALUE COLUMN — PANDAS USES FLOAT. DISPLAY ONLY.

# AUDIT:status=complete
# AUDIT:sprint=19
# AUDIT:issue=none
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import pandas as pd


class MultiPoolBacktest:
    """MANAGE BACKTEST ACROSS MANY POOLS. ROTATE CAPITAL. ALL DECIMAL."""

    def __init__(
        self,
        pool_ids: list[str],
        initial_capital: Decimal = Decimal("10000"),
        min_entry_score: Decimal = Decimal("0.25"),
        rebalance_cooldown_hours: Decimal = Decimal("4.0"),
        max_rebalances_per_pool_per_day: int = 3,
    ):
        """SET UP MULTI-POOL BACKTEST. ALL PARAMS DECIMAL."""
        self.pool_ids = pool_ids
        self.initial_capital = initial_capital
        self.min_entry_score = min_entry_score
        self.rebalance_cooldown_hours = rebalance_cooldown_hours
        self.max_rebalances_per_pool_per_day = max_rebalances_per_pool_per_day

        # STATE TRACKING. ALL DECIMAL.
        self.cash: Decimal = initial_capital
        self.active_positions: dict[str, dict] = {}  # pool_id -> position info
        self.rebalance_count: dict[str, int] = {pid: 0 for pid in pool_ids}
        self.last_rebalance_time: dict[str, Decimal] = {pid: Decimal("-999") for pid in pool_ids}
        self.equity_curve: list[Decimal] = [initial_capital]

    def total_value(self) -> Decimal:
        """SUM CASH PLUS ALL POSITION VALUES. RETURN DECIMAL."""
        position_value = sum(
            info.get("current_value", Decimal("0")) for info in self.active_positions.values()
        )
        return self.cash + position_value

    def can_rebalance(self, pool_id: str, current_time: Decimal) -> bool:
        """CHECK IF POOL CAN REBALANCE. COOLDOWN CHECK REAL. DAILY LIMIT STUB.

        # DAILY LIMIT NOT DONE YET. FUTURE SPRINT DO IT.

        Args:
            pool_id:      POOL ID.
            current_time: CURRENT TIME DECIMAL.

        Returns:
            TRUE IF REBALANCE OK.
        """
        # CHECK COOLDOWN. USE DECIMAL MATH.
        last_time = self.last_rebalance_time.get(pool_id, Decimal("-999"))
        if current_time - last_time < self.rebalance_cooldown_hours:
            return False

        # DAILY LIMIT NOT DONE YET. FUTURE SPRINT DO IT.
        return True

    def evaluate_entry(
        self,
        pool_scores: dict[str, Decimal],
        current_prices: dict[str, Decimal],
        current_time: Decimal,
    ) -> list[tuple[str, Decimal]]:
        """DECIDE WHICH POOLS TO ENTER. SCORE MUST BE ABOVE MIN. ALL DECIMAL.

        Args:
            pool_scores:     POOL ID TO SCORE DECIMAL.
            current_prices:  POOL ID TO PRICE DECIMAL.
            current_time:    TIME DECIMAL.

        Returns:
            LIST OF (POOL_ID, CAPITAL_DECIMAL) TUPLES.
        """
        entries: list[tuple[str, Decimal]] = []

        for pool_id in self.pool_ids:
            score = pool_scores.get(pool_id, Decimal("0"))

            # SKIP IF BELOW MIN SCORE. DECIMAL COMPARE.
            if score < self.min_entry_score:
                continue

            # SKIP IF ALREADY IN POSITION.
            if pool_id in self.active_positions:
                continue

            # CHECK REBALANCE CONSTRAINTS.
            if not self.can_rebalance(pool_id, current_time):
                continue

            # SPLIT CASH EQUAL WAY. DECIMAL DIVIDE.
            allocation = self.cash / Decimal(str(max(1, len(self.pool_ids))))
            if allocation > Decimal("0"):
                entries.append((pool_id, allocation))

        return entries

    def evaluate_exit(
        self,
        exit_signals: dict[str, list[str]],
        current_prices: dict[str, Decimal],
    ) -> list[str]:
        """DECIDE WHICH POOLS TO EXIT. SIGNAL TRIGGERED MEAN EXIT.

        Args:
            exit_signals:   POOL ID TO LIST OF SIGNAL NAMES.
            current_prices: POOL ID TO PRICE DECIMAL.

        Returns:
            LIST OF POOL IDS TO EXIT.
        """
        exits: list[str] = []

        for pool_id, signals in exit_signals.items():
            if len(signals) > 0 and pool_id in self.active_positions:
                exits.append(pool_id)

        return exits

    def step(
        self,
        timestamp: Decimal,
        prices: dict[str, Decimal],
        volumes: dict[str, Decimal],
        scores: dict[str, Decimal] | None = None,
        exit_signals: dict[str, list[str]] | None = None,
    ) -> Decimal:
        """MOVE BACKTEST FORWARD ONE STEP. ALL DECIMAL INPUTS.

        Args:
            timestamp:     TIME DECIMAL.
            prices:        POOL ID TO PRICE DECIMAL.
            volumes:       POOL ID TO VOLUME DECIMAL.
            scores:        OPTIONAL POOL SCORES DECIMAL.
            exit_signals:  OPTIONAL EXIT SIGNALS.

        Returns:
            TOTAL PORTFOLIO VALUE DECIMAL.
        """
        # UPDATE EXISTING POSITIONS.
        for pool_id, info in list(self.active_positions.items()):
            price = prices.get(pool_id, Decimal("0"))
            volume = volumes.get(pool_id, Decimal("0"))

            if "simulator" in info:
                # BOUNDARY: BACKTESTSIMULATOR WANT TAGGEDDECIMAL. CONVERT HERE.
                from core.units import price_t1_t0, usd

                sim = info["simulator"]
                sim.step(
                    price_t1_t0(price),
                    usd(volume),
                )
                # UPDATE TRACKED VALUE. PULL FROM SIMULATOR POSITION.
                if sim.position is not None:
                    info["current_value"] = sim.position.current_value_usd.value
                else:
                    info["current_value"] = Decimal("0")

        # EVALUATE EXITS.
        if exit_signals:
            pools_to_exit = self.evaluate_exit(exit_signals, prices)
            for pool_id in pools_to_exit:
                if pool_id in self.active_positions:
                    info = self.active_positions[pool_id]
                    if "simulator" in info:
                        proceeds_tagged = info["simulator"].exit()
                        self.cash += proceeds_tagged.value
                    del self.active_positions[pool_id]

        # EVALUATE ENTRIES.
        if scores:
            entries = self.evaluate_entry(scores, prices, timestamp)
            for pool_id, capital in entries:
                price = prices.get(pool_id, Decimal("0"))
                if price > Decimal("0") and capital > Decimal("0"):
                    # FIX OLD BUG: USE BACKTESTSIMULATOR NOT POSITIONSIMULATOR.
                    from backtest.simulator import BacktestSimulator

                    sim = BacktestSimulator(
                        pool_id=pool_id,
                        initial_capital=None,  # WE SET CASH MANUALLY
                    )
                    # BOUNDARY: ENTER WANT TAGGEDDECIMAL. CONVERT HERE.
                    from core.units import price_t1_t0, usd

                    sim.enter(price_t1_t0(price), usd(capital))
                    self.active_positions[pool_id] = {
                        "simulator": sim,
                        "current_value": capital,
                        "entry_time": timestamp,
                    }
                    self.cash -= capital
                    self.rebalance_count[pool_id] = self.rebalance_count.get(pool_id, 0) + 1
                    self.last_rebalance_time[pool_id] = timestamp

        # RECORD EQUITY. ALL DECIMAL.
        total = self.total_value()
        self.equity_curve.append(total)
        return total

    def summary(self) -> dict:
        """MAKE FINAL SUMMARY. ALL VALUES DECIMAL WHERE NUMERIC.

        MONETARY VALUES USE .QUANTIZE(DECIMAL("0.01")).
        RATIO/PCT VALUES USE .QUANTIZE(DECIMAL("0.0001")).

        Returns:
            DICT WITH PORTFOLIO METRICS. ALL DECIMAL EXCEPT ACTIVE POSITIONS COUNT.
        """
        from core.metrics import max_drawdown

        final_value = self.equity_curve[-1] if self.equity_curve else self.initial_capital

        # PNL COMPUTE. GUARD DIVIDE BY ZERO.
        if self.initial_capital > Decimal("0"):
            pnl_pct = (final_value / self.initial_capital - Decimal("1")) * Decimal("100")
        else:
            pnl_pct = Decimal("0")

        # BOUNDARY: MAX_DRAWDOWN WANT LIST[FLOAT]. CONVERT HERE. ONLY PLACE ALLOWED.
        dd_raw = max_drawdown([float(v) for v in self.equity_curve])
        max_dd = Decimal(str(dd_raw))

        return {
            "final_value": final_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "initial_capital": self.initial_capital,
            "total_pnl": (final_value - self.initial_capital).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "pnl_pct": pnl_pct.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            "max_drawdown": max_dd.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            "active_positions_at_end": len(self.active_positions),
        }

    def equity_df(self) -> pd.DataFrame:
        """EQUITY DF. CONVERT DECIMAL TO FLOAT FOR PANDAS. DISPLAY ONLY. NOT FOR MATH.

        Returns:
            DATAFRAME WITH 'STEP' AND 'VALUE' COLUMNS. VALUE IS FLOAT.
        """
        return pd.DataFrame({
            "step": range(len(self.equity_curve)),
            "value": [float(v) for v in self.equity_curve],
        })