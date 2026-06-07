"""TEST SIGNAL. DECIMAL INPUT. DECIMAL MATH. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=17

from __future__ import annotations

from decimal import Decimal

import pytest

from strategy.signals import (
    DrawdownSignal,
    ILFeeRatioSignal,
    MomentumCrashSignal,
    TVLCollapseSignal,
    any_exit_signal,
    signal_a_drawdown,
    signal_b_momentum_crash,
    signal_c_tvl_collapse,
    signal_d_il_fee_ratio,
)

_D = Decimal


# ── signal_a_drawdown ─────────────────────────────────────────────────

def test_signal_a_triggers_at_threshold():
    assert signal_a_drawdown(_D("85"), _D("100"), _D("0.15")) is True


def test_signal_a_no_trigger_below_threshold():
    assert signal_a_drawdown(_D("90"), _D("100"), _D("0.15")) is False


def test_signal_a_zero_peak_returns_false():
    assert signal_a_drawdown(_D("0"), _D("0"), _D("0.15")) is False


def test_signal_a_decimal_types():
    result = signal_a_drawdown(_D("80"), _D("100"), _D("0.15"))
    assert isinstance(result, bool)


# ── signal_b_momentum_crash ───────────────────────────────────────────

def test_signal_b_triggers_on_crash():
    returns = [_D("-0.04"), _D("-0.05"), _D("-0.06")]
    assert signal_b_momentum_crash(returns, _D("0.03"), 3) is True


def test_signal_b_no_trigger_mild_returns():
    returns = [_D("-0.01"), _D("-0.01"), _D("-0.01")]
    assert signal_b_momentum_crash(returns, _D("0.03"), 3) is False


def test_signal_b_insufficient_data_returns_false():
    returns = [_D("-0.05"), _D("-0.05")]
    assert signal_b_momentum_crash(returns, _D("0.03"), 3) is False


def test_signal_b_uses_only_last_n():
    # ONLY LAST 3 MATTER. EARLY DATA BIG BUT IGNORED.
    returns = [_D("0.10"), _D("0.10"), _D("-0.01"), _D("-0.01"), _D("-0.01")]
    assert signal_b_momentum_crash(returns, _D("0.03"), 3) is False


# ── signal_c_tvl_collapse ─────────────────────────────────────────────

def test_signal_c_triggers_on_collapse():
    assert signal_c_tvl_collapse(_D("600000"), _D("1000000"), _D("-0.30")) is True


def test_signal_c_no_trigger_small_drop():
    assert signal_c_tvl_collapse(_D("800000"), _D("1000000"), _D("-0.30")) is False


def test_signal_c_zero_reference_returns_false():
    assert signal_c_tvl_collapse(_D("0"), _D("0"), _D("-0.30")) is False


# ── signal_d_il_fee_ratio ─────────────────────────────────────────────

def test_signal_d_triggers_when_ratio_high():
    assert signal_d_il_fee_ratio(_D("80"), _D("10"), _D("8.0"), _D("24.0"), _D("24.0")) is True


def test_signal_d_no_trigger_below_ratio():
    assert signal_d_il_fee_ratio(_D("70"), _D("10"), _D("8.0"), _D("24.0"), _D("24.0")) is False


def test_signal_d_no_trigger_before_hold_hours():
    assert signal_d_il_fee_ratio(_D("80"), _D("10"), _D("8.0"), _D("24.0"), _D("12.0")) is False


def test_signal_d_zero_fees_triggers_when_il_positive():
    assert signal_d_il_fee_ratio(_D("1"), _D("0"), _D("8.0"), _D("24.0"), _D("24.0")) is True


def test_signal_d_zero_fees_no_trigger_when_il_zero():
    assert signal_d_il_fee_ratio(_D("0"), _D("0"), _D("8.0"), _D("24.0"), _D("24.0")) is False


# ── DrawdownSignal class ──────────────────────────────────────────────

def test_drawdown_signal_default_threshold_is_decimal():
    sig = DrawdownSignal()
    assert isinstance(sig.threshold, Decimal)


def test_drawdown_signal_check_triggers():
    sig = DrawdownSignal(threshold=_D("0.15"))
    assert sig.check(_D("80"), _D("100")) is True


# ── MomentumCrashSignal class ─────────────────────────────────────────

def test_momentum_crash_signal_from_prices():
    sig = MomentumCrashSignal(lookback_hrs=3, threshold=_D("0.03"))
    prices = [_D("100"), _D("95"), _D("90"), _D("84")]
    assert sig.check(prices) is True


def test_momentum_crash_signal_insufficient_prices():
    sig = MomentumCrashSignal()
    assert sig.check([_D("100")]) is False


# ── TVLCollapseSignal class ───────────────────────────────────────────

def test_tvl_collapse_signal_default_threshold_is_decimal():
    sig = TVLCollapseSignal()
    assert isinstance(sig.threshold, Decimal)


def test_tvl_collapse_signal_triggers():
    sig = TVLCollapseSignal(threshold=_D("-0.30"))
    assert sig.check(_D("600000"), _D("1000000")) is True


# ── ILFeeRatioSignal class ────────────────────────────────────────────

def test_il_fee_ratio_signal_triggers():
    sig = ILFeeRatioSignal(threshold=_D("8.0"))
    # RATIO AT THRESHOLD TRIGGER (>=). 0.80/0.10=8.0 >= 8.0 IS TRUE.
    assert sig.check(_D("0.80"), _D("0.10")) is True
    assert sig.check(_D("0.79"), _D("0.10")) is False  # BELOW THRESHOLD


# ── any_exit_signal ───────────────────────────────────────────────────

def test_any_exit_signal_returns_list():
    result = any_exit_signal(
        current_value=_D("100"), peak_value=_D("100"),
        hourly_returns=[_D("0.01"), _D("0.01"), _D("0.01")],
        tvl_current=_D("1000000"), tvl_reference=_D("1000000"),
        il_loss_usd=_D("0"), fees_earned_usd=_D("10"),
    )
    assert isinstance(result, list)


def test_any_exit_signal_drawdown_triggered():
    result = any_exit_signal(
        current_value=_D("80"), peak_value=_D("100"),
        hourly_returns=[_D("0.0")] * 3,
        tvl_current=_D("1000000"), tvl_reference=_D("1000000"),
        il_loss_usd=_D("0"), fees_earned_usd=_D("10"),
    )
    assert "drawdown" in result


def test_any_exit_signal_cfg_overrides_threshold():
    """CFG DICT OVERRIDE THRESHOLD. DRAWDOWN 0.05 TRIGGER WHEN THRESHOLD SET LOW."""
    result = any_exit_signal(
        current_value=_D("96"), peak_value=_D("100"),
        hourly_returns=[_D("0.0")] * 3,
        tvl_current=_D("1000000"), tvl_reference=_D("1000000"),
        il_loss_usd=_D("0"), fees_earned_usd=_D("10"),
        cfg={"drawdown_pct": "0.03"},
    )
    assert "drawdown" in result


def test_any_exit_signal_no_triggers_returns_empty():
    result = any_exit_signal(
        current_value=_D("100"), peak_value=_D("100"),
        hourly_returns=[_D("0.01")] * 3,
        tvl_current=_D("1000000"), tvl_reference=_D("1000000"),
        il_loss_usd=_D("0"), fees_earned_usd=_D("10"),
        position_hours=_D("1.0"),
    )
    assert result == []