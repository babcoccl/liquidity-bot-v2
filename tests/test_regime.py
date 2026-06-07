"""TEST REGIME. DECIMAL INPUT. CORRECT CLASSIFICATION. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=17

from __future__ import annotations

from decimal import Decimal

import pytest

from strategy.regime import (
    RegimeClassifier,
    allocation_adjustment,
    classify_regime,
    optimal_range_width,
    regime_summary,
)

_D = Decimal


# ── classify_regime ───────────────────────────────────────────────────

def test_classify_regime_low_vol_no_trend():
    assert classify_regime(_D("0.10"), _D("0.10")) == "low_vol_no_trend"


def test_classify_regime_low_vol_trend():
    assert classify_regime(_D("0.10"), _D("0.50")) == "low_vol_trend"


def test_classify_regime_high_vol_no_trend():
    assert classify_regime(_D("0.70"), _D("0.10")) == "high_vol_no_trend"


def test_classify_regime_high_vol_trend():
    assert classify_regime(_D("0.70"), _D("0.50")) == "high_vol_trend"


def test_classify_regime_boundary_vol_low():
    # AT BOUNDARY. vol=0.20 IS STILL LOW.
    assert classify_regime(_D("0.20"), _D("0.10")) == "low_vol_no_trend"


def test_classify_regime_boundary_vol_high():
    # AT HIGH BOUNDARY. vol=0.60 IS HIGH.
    assert classify_regime(_D("0.60"), _D("0.10")) == "high_vol_no_trend"


def test_classify_regime_decimal_inputs_only():
    result = classify_regime(_D("0.3"), _D("0.2"))
    assert isinstance(result, str)


# ── optimal_range_width ───────────────────────────────────────────────

def test_optimal_range_width_low_vol_no_trend_wider():
    w = optimal_range_width("low_vol_no_trend", _D("0.10"), _D("0.10"))
    assert isinstance(w, Decimal)
    assert w >= _D("0.05")


def test_optimal_range_width_high_vol_trend_tighter():
    wide = optimal_range_width("high_vol_no_trend", _D("0.70"), _D("0.10"))
    tight = optimal_range_width("high_vol_trend", _D("0.70"), _D("0.10"))
    assert tight < wide


def test_optimal_range_width_unknown_regime_returns_base():
    base = _D("0.10")
    result = optimal_range_width("unknown_regime", _D("0.50"), base)
    assert result == base


def test_optimal_range_width_returns_decimal():
    result = optimal_range_width("low_vol_trend", _D("0.15"), _D("0.10"))
    assert isinstance(result, Decimal)


# ── allocation_adjustment ─────────────────────────────────────────────

def test_allocation_adjustment_low_vol_no_trend_increases():
    result = allocation_adjustment("low_vol_no_trend", _D("0.5"))
    assert result > _D("0.5")


def test_allocation_adjustment_high_vol_no_trend_decreases():
    result = allocation_adjustment("high_vol_no_trend", _D("0.5"))
    assert result < _D("0.5")


def test_allocation_adjustment_capped_at_one():
    result = allocation_adjustment("low_vol_no_trend", _D("1.0"))
    assert result <= _D("1.0")


def test_allocation_adjustment_returns_decimal():
    result = allocation_adjustment("low_vol_trend", _D("0.5"))
    assert isinstance(result, Decimal)


def test_allocation_adjustment_unknown_regime_neutral():
    result = allocation_adjustment("unknown", _D("0.5"))
    assert result == _D("0.5")


def test_allocation_adjustment_custom_multipliers():
    m = {"test_regime": _D("2.0")}
    result = allocation_adjustment("test_regime", _D("0.3"), multipliers=m)
    assert result == _D("0.6")


# ── RegimeClassifier class ────────────────────────────────────────────

def test_regime_classifier_default_thresholds_are_decimal():
    rc = RegimeClassifier()
    assert isinstance(rc.vol_threshold_low, Decimal)
    assert isinstance(rc.vol_threshold_high, Decimal)
    assert isinstance(rc.trend_threshold, Decimal)


def test_regime_classifier_classify_delegates():
    rc = RegimeClassifier()
    assert rc.classify(_D("0.10"), _D("0.10")) == "low_vol_no_trend"


def test_regime_classifier_classify_uses_abs_trend():
    rc = RegimeClassifier()
    # NEGATIVE TREND SAME AS POSITIVE TREND. ABS APPLIED.
    assert rc.classify(_D("0.10"), _D("-0.50")) == "low_vol_trend"


# ── regime_summary ────────────────────────────────────────────────────

def test_regime_summary_returns_dict_with_required_keys():
    result = regime_summary(_D("0.10"), _D("0.10"))
    required = {"regime", "volatility", "trend_strength", "recommended_range_width", "adjusted_allocation"}
    assert required.issubset(result.keys())


def test_regime_summary_values_are_decimal_except_regime():
    result = regime_summary(_D("0.10"), _D("0.10"))
    assert isinstance(result["regime"], str)
    assert isinstance(result["volatility"], Decimal)
    assert isinstance(result["trend_strength"], Decimal)
    assert isinstance(result["recommended_range_width"], Decimal)
    assert isinstance(result["adjusted_allocation"], Decimal)