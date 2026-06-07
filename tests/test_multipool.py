# AUDIT:status=complete
# AUDIT:sprint=19

"""TESTS FOR MULTI-POOL BACKTEST. ALL INPUTS DECIMAL. NO FLOAT IN TEST BODIES."""

from __future__ import annotations

import pytest
from decimal import Decimal

from backtest.multipool import MultiPoolBacktest


# ---- INIT / STATE TESTS ----

def test_init_cash_is_decimal() -> None:
    """CASH MUST BE DECIMAL TYPE AFTER INIT."""
    mp = MultiPoolBacktest(["A"], initial_capital=Decimal("5000"))
    assert isinstance(mp.cash, Decimal)
    assert mp.cash == Decimal("5000")


def test_init_equity_curve_starts_with_initial_capital() -> None:
    """EQUITY CURVE START WITH INITIAL CAPITAL AS FIRST ELEMENT."""
    cap = Decimal("7500")
    mp = MultiPoolBacktest(["X"], initial_capital=cap)
    assert mp.equity_curve[0] == cap


def test_init_rebalance_count_zeroed_for_all_pools() -> None:
    """REBALANCE COUNT ZERO FOR ALL POOLS."""
    pools = ["A", "B", "C"]
    mp = MultiPoolBacktest(pools)
    for pid in pools:
        assert pid in mp.rebalance_count
        assert mp.rebalance_count[pid] == 0


def test_init_last_rebalance_time_sentinel() -> None:
    """LAST REBALANCE TIME USE SENTINEL -999 FOR ALL POOLS."""
    pools = ["P1", "P2"]
    mp = MultiPoolBacktest(pools)
    for pid in pools:
        assert mp.last_rebalance_time[pid] == Decimal("-999")


# ---- TOTAL_VALUE TESTS ----

def test_total_value_no_positions_equals_cash() -> None:
    """NO POSITION MEAN TOTAL VALUE EQUAL CASH."""
    cap = Decimal("3000")
    mp = MultiPoolBacktest(["Z"], initial_capital=cap)
    assert mp.total_value() == cap


def test_total_value_returns_decimal() -> None:
    """TOTAL_VALUE RETURN DECIMAL TYPE."""
    mp = MultiPoolBacktest(["A"])
    result = mp.total_value()
    assert isinstance(result, Decimal)


def test_total_value_includes_active_position_value() -> None:
    """TOTAL VALUE INCLUDE ACTIVE POSITION CURRENT_VALUE."""
    mp = MultiPoolBacktest(["A"], initial_capital=Decimal("1000"))
    # INJECT FAKE POSITION WITH CURRENT_VALUE.
    mp.active_positions["A"] = {"current_value": Decimal("500")}
    assert mp.total_value() == Decimal("1500")


# ---- CAN_REBALANCE TESTS ----

def test_can_rebalance_respects_cooldown() -> None:
    """COOLDOWN BLOCK REBALANCE WHEN NOT ENOUGH TIME PASS."""
    mp = MultiPoolBacktest(["A"], rebalance_cooldown_hours=Decimal("4"))
    mp.last_rebalance_time["A"] = Decimal("0")
    assert mp.can_rebalance("A", Decimal("3")) is False


def test_can_rebalance_after_cooldown() -> None:
    """REBALANCE OK AFTER COOLDOWN PASS."""
    mp = MultiPoolBacktest(["A"], rebalance_cooldown_hours=Decimal("4"))
    mp.last_rebalance_time["A"] = Decimal("0")
    assert mp.can_rebalance("A", Decimal("5")) is True


def test_can_rebalance_unknown_pool_uses_sentinel() -> None:
    """UNKNOWN POOL USE SENTINEL SO ANY REASONABLE TIME RETURN TRUE."""
    mp = MultiPoolBacktest(["A"])
    # "B" NOT IN last_rebalance_time. USE SENTINEL -999.
    assert mp.can_rebalance("B", Decimal("10")) is True


# ---- EVALUATE_ENTRY TESTS ----

def test_evaluate_entry_filters_below_min_score() -> None:
    """POOL WITH SCORE BELOW MIN NOT IN RESULT."""
    mp = MultiPoolBacktest(["A"], min_entry_score=Decimal("0.5"))
    entries = mp.evaluate_entry(
        pool_scores={"A": Decimal("0.3")},
        current_prices={"A": Decimal("100")},
        current_time=Decimal("10"),
    )
    pool_ids_in_result = [e[0] for e in entries]
    assert "A" not in pool_ids_in_result


def test_evaluate_entry_skips_already_active() -> None:
    """POOL ALREADY IN POSITION NOT RETURN EVEN WITH HIGH SCORE."""
    mp = MultiPoolBacktest(["A"], min_entry_score=Decimal("0.1"))
    mp.active_positions["A"] = {"current_value": Decimal("100")}
    entries = mp.evaluate_entry(
        pool_scores={"A": Decimal("0.9")},
        current_prices={"A": Decimal("100")},
        current_time=Decimal("10"),
    )
    pool_ids_in_result = [e[0] for e in entries]
    assert "A" not in pool_ids_in_result


def test_evaluate_entry_returns_decimal_allocation() -> None:
    """ALLOCATION MUST BE DECIMAL TYPE."""
    mp = MultiPoolBacktest(["A"], min_entry_score=Decimal("0.1"))
    entries = mp.evaluate_entry(
        pool_scores={"A": Decimal("0.5")},
        current_prices={"A": Decimal("100")},
        current_time=Decimal("10"),
    )
    assert len(entries) == 1
    assert isinstance(entries[0][1], Decimal)


def test_evaluate_entry_allocation_positive() -> None:
    """ALLOCATION MUST BE GREATER THAN ZERO."""
    mp = MultiPoolBacktest(["A"], min_entry_score=Decimal("0.1"))
    entries = mp.evaluate_entry(
        pool_scores={"A": Decimal("0.5")},
        current_prices={"A": Decimal("100")},
        current_time=Decimal("10"),
    )
    assert len(entries) == 1
    assert entries[0][1] > Decimal("0")


# ---- EVALUATE_EXIT TESTS ----

def test_evaluate_exit_triggered_signal_exits() -> None:
    """POOL WITH SIGNAL AND IN POSITION GET EXIT."""
    mp = MultiPoolBacktest(["A"])
    mp.active_positions["A"] = {"current_value": Decimal("100")}
    exits = mp.evaluate_exit(
        exit_signals={"A": ["stop_loss"]},
        current_prices={"A": Decimal("50")},
    )
    assert "A" in exits


def test_evaluate_exit_no_signal_no_exit() -> None:
    """EMPTY SIGNAL LIST MEAN NO EXIT."""
    mp = MultiPoolBacktest(["A"])
    mp.active_positions["A"] = {"current_value": Decimal("100")}
    exits = mp.evaluate_exit(
        exit_signals={"A": []},
        current_prices={"A": Decimal("50")},
    )
    assert "A" not in exits


def test_evaluate_exit_not_in_positions_not_in_result() -> None:
    """SIGNAL TRIGGERED BUT POOL NOT IN POSITION MEAN NO EXIT."""
    mp = MultiPoolBacktest(["A"])
    # DO NOT ADD A TO ACTIVE POSITIONS.
    exits = mp.evaluate_exit(
        exit_signals={"A": ["stop_loss"]},
        current_prices={"A": Decimal("50")},
    )
    assert "A" not in exits


# ---- STEP TESTS ----

def test_step_returns_decimal() -> None:
    """STEP RETURN DECIMAL TYPE."""
    mp = MultiPoolBacktest(["A"])
    result = mp.step(Decimal("1"), {}, {})
    assert isinstance(result, Decimal)


def test_step_appends_to_equity_curve() -> None:
    """ONE STEP ADD ONE MORE ELEMENT TO EQUITY CURVE."""
    mp = MultiPoolBacktest(["A"])
    initial_len = len(mp.equity_curve)
    mp.step(Decimal("1"), {}, {})
    assert len(mp.equity_curve) == initial_len + 1


def test_step_no_positions_value_unchanged() -> None:
    """STEP WITH NO SCORES NO SIGNALS NO POSITIONS RETURN INITIAL CAPITAL."""
    cap = Decimal("8000")
    mp = MultiPoolBacktest(["A"], initial_capital=cap)
    result = mp.step(Decimal("1"), {}, {})
    assert result == cap


# ---- SUMMARY TESTS ----

def test_summary_returns_required_keys() -> None:
    """SUMMARY DICT HAVE ALL REQUIRED KEYS."""
    mp = MultiPoolBacktest(["A"])
    s = mp.summary()
    required = [
        "final_value",
        "initial_capital",
        "total_pnl",
        "pnl_pct",
        "max_drawdown",
        "active_positions_at_end",
    ]
    for key in required:
        assert key in s, f"MISSING KEY: {key}"


def test_summary_pnl_is_decimal() -> None:
    """TOTAL_PNL IN SUMMARY MUST BE DECIMAL."""
    mp = MultiPoolBacktest(["A"])
    s = mp.summary()
    assert isinstance(s["total_pnl"], Decimal)


def test_summary_no_gain_pnl_zero() -> None:
    """FRESH INSTANCE WITH NO STEPS HAVE PNL ZERO."""
    mp = MultiPoolBacktest(["A"], initial_capital=Decimal("10000"))
    s = mp.summary()
    assert s["total_pnl"] == Decimal("0.00")


# ---- EQUITY_DF TESTS ----

def test_equity_df_has_correct_columns() -> None:
    """EQUITY DF HAVE STEP AND VALUE COLUMNS."""
    mp = MultiPoolBacktest(["A"])
    df = mp.equity_df()
    assert list(df.columns) == ["step", "value"]


def test_equity_df_value_column_is_float() -> None:
    """VALUE COLUMN MUST BE FLOAT TYPE FOR PANDAS COMPATIBILITY."""
    mp = MultiPoolBacktest(["A"])
    df = mp.equity_df()
    # PANDAS DTYPE FOR FLOAT COLUMN START WITH 'float'.
    assert str(df["value"].dtype).startswith("float")