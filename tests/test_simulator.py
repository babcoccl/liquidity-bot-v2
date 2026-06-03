"""Tests for backtest.simulator — Position, PositionSimulator, BacktestSimulator."""

import pytest
from decimal import Decimal

from core.units import TaggedDecimal, DenominationError, usd, bps, price_t1_t0, ratio
from core.models import PoolDayData


# ============================================================================
# Helpers
# ============================================================================

def _make_record(
    price: str = "2000",
    volume: str = "500000",
    tvl: str = "10000000",
    date: int = 1700000000,
    pool_address: str = "0xpool",
) -> PoolDayData:
    return PoolDayData(
        pool_address=pool_address,
        date=date,
        price_token1_in_token0=Decimal(price),
        price_token0_in_token1=Decimal("1") / Decimal(price),
        volume_usd=Decimal(volume),
        tvl_usd=Decimal(tvl),
        fee_growth_global_0=None,
        fee_growth_global_1=None,
        source="the_graph",
    )


# ============================================================================
# Position tests
# ============================================================================

class TestPosition:

    def _make_position(
        self,
        entry_price: str = "2000",
        price_lower: str = "1800",
        price_upper: str = "2200",
        capital: str = "10000",
        fee_bps: str = "30",
    ):
        from backtest.simulator import Position
        return Position(
            pool_id="0xpool",
            entry_price=price_t1_t0(entry_price),
            price_lower=price_t1_t0(price_lower),
            price_upper=price_t1_t0(price_upper),
            capital_usd=usd(capital),
            fee_tier_bps=bps(fee_bps),
        )

    def test_position_initial_value_equals_capital(self):
        pos = self._make_position()
        assert pos.current_value_usd == usd("10000")

    def test_position_initial_fees_are_zero(self):
        pos = self._make_position()
        assert pos.fees_earned_usd == usd("0")

    def test_position_last_price_initialized_to_entry(self):
        pos = self._make_position(entry_price="2000")
        assert pos.last_price == price_t1_t0("2000")

    def test_position_update_records_last_price(self):
        pos = self._make_position(entry_price="2000")
        pos.update(
            current_price=price_t1_t0("2100"),
            volume_usd=usd("500000"),
            pool_tvl_usd=usd("10000000"),
        )
        assert pos.last_price == price_t1_t0("2100")

    def test_position_update_accumulates_fees(self):
        pos = self._make_position()
        pos.update(
            current_price=price_t1_t0("2000"),
            volume_usd=usd("500000"),
            pool_tvl_usd=usd("10000000"),
        )
        assert pos.fees_earned_usd.value > Decimal("0")
        assert pos.fees_earned_usd.denom == "USD"

    def test_position_update_current_value_is_usd(self):
        pos = self._make_position()
        pos.update(
            current_price=price_t1_t0("2000"),
            volume_usd=usd("500000"),
            pool_tvl_usd=usd("10000000"),
        )
        assert pos.current_value_usd.denom == "USD"

    def test_position_zero_volume_earns_zero_fees(self):
        pos = self._make_position()
        pos.update(
            current_price=price_t1_t0("2000"),
            volume_usd=usd("0"),
            pool_tvl_usd=usd("10000000"),
        )
        assert pos.fees_earned_usd == usd("0")

    def test_position_out_of_range_above_still_updates(self):
        # Price far above range — IL should result in lower value, fees still accrue
        pos = self._make_position(
            entry_price="2000", price_lower="1800", price_upper="2200"
        )
        pos.update(
            current_price=price_t1_t0("5000"),
            volume_usd=usd("500000"),
            pool_tvl_usd=usd("10000000"),
        )
        # Should not raise; current_value_usd must remain a USD TaggedDecimal
        assert pos.current_value_usd.denom == "USD"


# ============================================================================
# PositionSimulator tests
# ============================================================================

class TestPositionSimulator:

    def _make_simulator(self, **kwargs):
        from backtest.simulator import PositionSimulator
        return PositionSimulator(pool_id="0xpool", **kwargs)

    def test_step_returns_usd_tagged_decimal(self):
        sim = self._make_simulator()
        result = sim.step(_make_record())
        assert isinstance(result, TaggedDecimal)
        assert result.denom == "USD"

    def test_step_opens_position_on_first_call(self):
        sim = self._make_simulator()
        sim.step(_make_record())
        assert sim.position is not None

    def test_step_cash_is_zero_after_first_step(self):
        sim = self._make_simulator()
        sim.step(_make_record())
        assert sim.cash == usd("0")

    def test_step_equity_curve_appended_each_step(self):
        sim = self._make_simulator()
        sim.step(_make_record(date=1700000000))
        sim.step(_make_record(date=1700086400))
        sim.step(_make_record(date=1700172800))
        # Initial value + 3 steps = 4 entries
        assert len(sim.equity_curve) == 4

    def test_step_equity_curve_all_usd(self):
        sim = self._make_simulator()
        sim.step(_make_record())
        assert all(v.denom == "USD" for v in sim.equity_curve)

    def test_step_position_price_range_uses_multipliers(self):
        sim = self._make_simulator(
            price_lower_multiplier=Decimal("0.8"),
            price_upper_multiplier=Decimal("1.2"),
        )
        sim.step(_make_record(price="2000"))
        assert sim.position.price_lower.value == Decimal("2000") * Decimal("0.8")
        assert sim.position.price_upper.value == Decimal("2000") * Decimal("1.2")

    def test_step_uses_initial_capital_as_tvl_fallback_when_tvl_zero(self):
        """When record.tvl_usd == 0, tvl falls back to initial_usd — no ZeroDivisionError."""
        sim = self._make_simulator(initial_usd=usd("10000"))
        # Should not raise even with zero TVL
        result = sim.step(_make_record(tvl="0"))
        assert result.denom == "USD"

    def test_multiple_steps_same_price_fees_accumulate(self):
        sim = self._make_simulator()
        sim.step(_make_record(date=1700000000))
        val_after_1 = sim.position.fees_earned_usd.value
        sim.step(_make_record(date=1700086400))
        val_after_2 = sim.position.fees_earned_usd.value
        assert val_after_2 > val_after_1


# ============================================================================
# BacktestSimulator tests
# ============================================================================

class TestBacktestSimulator:

    def _make_simulator(self, **kwargs):
        from backtest.simulator import BacktestSimulator
        return BacktestSimulator(pool_id="0xpool", **kwargs)

    def test_enter_opens_position(self):
        sim = self._make_simulator()
        sim.enter(entry_price=price_t1_t0("2000"))
        assert sim.position is not None

    def test_enter_depletes_cash(self):
        sim = self._make_simulator(initial_capital=usd("10000"))
        sim.enter(entry_price=price_t1_t0("2000"))
        assert sim.cash == usd("0")

    def test_enter_twice_is_noop(self):
        sim = self._make_simulator()
        sim.enter(entry_price=price_t1_t0("2000"))
        first_position = sim.position
        sim.enter(entry_price=price_t1_t0("2100"))
        assert sim.position is first_position

    def test_exit_returns_usd(self):
        sim = self._make_simulator()
        sim.enter(entry_price=price_t1_t0("2000"))
        proceeds = sim.exit()
        assert proceeds.denom == "USD"

    def test_exit_with_no_position_returns_zero(self):
        sim = self._make_simulator()
        result = sim.exit()
        assert result == usd("0")

    def test_exit_restores_cash(self):
        sim = self._make_simulator(initial_capital=usd("10000"))
        sim.enter(entry_price=price_t1_t0("2000"))
        sim.exit()
        assert sim.cash.value > Decimal("0")
        assert sim.position is None

    def test_step_returns_usd(self):
        sim = self._make_simulator()
        sim.enter(entry_price=price_t1_t0("2000"))
        result = sim.step(
            current_price=price_t1_t0("2000"),
            volume=usd("500000"),
        )
        assert result.denom == "USD"

    def test_step_with_no_position_returns_cash(self):
        sim = self._make_simulator(initial_capital=usd("10000"))
        result = sim.step(
            current_price=price_t1_t0("2000"),
            volume=usd("500000"),
        )
        assert result == usd("10000")

    def test_summary_returns_expected_keys(self):
        sim = self._make_simulator()
        sim.enter(entry_price=price_t1_t0("2000"))
        sim.step(current_price=price_t1_t0("2000"), volume=usd("500000"))
        summary = sim.summary()
        for key in ["initial_capital", "final_value", "total_pnl", "pnl_pct",
                    "max_drawdown", "total_fees_earned", "total_il_loss"]:
            assert key in summary, f"Missing key: {key}"

    def test_summary_il_uses_last_price_not_value_ratio(self):
        """
        Regression test for the Sprint 7 hotfix.
        summary() must use position.last_price for IL computation,
        not current_value / capital (which is not a price).
        With stable price and 10% range, IL should be near zero.
        """
        sim = self._make_simulator(initial_capital=usd("10000"))
        sim.enter(entry_price=price_t1_t0("2000"))
        sim.step(current_price=price_t1_t0("2000"), volume=usd("500000"))
        summary = sim.summary()
        # IL at same price should be effectively 0
        assert abs(summary["total_il_loss"]) < 1.0

    def test_summary_il_nonzero_after_price_move(self):
        """IL should be non-zero after a significant price move."""
        sim = self._make_simulator(initial_capital=usd("10000"))
        sim.enter(entry_price=price_t1_t0("2000"))
        sim.step(current_price=price_t1_t0("2000"), volume=usd("500000"))
        sim.step(current_price=price_t1_t0("3000"), volume=usd("500000"))
        summary = sim.summary()
        assert summary["total_il_loss"] != 0.0