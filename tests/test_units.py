"""Tests for core.units — TaggedDecimal denomination enforcement."""

import pytest
from decimal import Decimal
from core.units import (
    TaggedDecimal,
    DenominationError,
    MULTIPLY_RULES,
    usd,
    token0,
    token1,
    price_t1_t0,
    price_t0_t1,
    bps,
    ratio,
    raw_q128,
)


# ── TestTaggedDecimalConstruction ────────────────────────────────────────────

class TestTaggedDecimalConstruction:
    def test_tagged_decimal_stores_value_as_decimal(self) -> None:
        t = TaggedDecimal(Decimal("42"), "USD")
        assert t.value == Decimal("42")
        assert isinstance(t.value, Decimal)

    def test_tagged_decimal_coerces_float_to_decimal(self) -> None:
        t = TaggedDecimal(3.14, "RATIO")
        assert t.value == Decimal("3.14")
        assert isinstance(t.value, Decimal)

    def test_tagged_decimal_coerces_string_to_decimal(self) -> None:
        t = TaggedDecimal("99.5", "USD")
        assert t.value == Decimal("99.5")

    def test_tagged_decimal_empty_denom_raises(self) -> None:
        with pytest.raises(DenominationError, match="denom must be a non-empty string"):
            TaggedDecimal(Decimal("1"), "")

    def test_tagged_decimal_is_frozen(self) -> None:
        t = usd("10")
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            t.value = Decimal("20")


# ── TestTaggedDecimalArithmetic ──────────────────────────────────────────────

class TestTaggedDecimalArithmetic:
    def test_add_same_denom_returns_correct_value(self) -> None:
        result = usd("10") + usd("20")
        assert result.value == Decimal("30")

    def test_add_same_denom_preserves_denom(self) -> None:
        result = usd("10") + usd("20")
        assert result.denom == "USD"

    def test_add_different_denom_raises_denomination_error(self) -> None:
        with pytest.raises(DenominationError, match="incompatible"):
            usd("10") + token0("5")

    def test_sub_same_denom_correct(self) -> None:
        result = usd("30") - usd("12")
        assert result.value == Decimal("18")
        assert result.denom == "USD"

    def test_sub_different_denom_raises(self) -> None:
        with pytest.raises(DenominationError):
            token1("5") - token0("3")

    def test_mul_price_times_token1_returns_token0(self) -> None:
        # PRICE_T1_T0 * TOKEN1 → TOKEN0
        result = price_t1_t0("2000") * token1("3")
        assert result.denom == "TOKEN0"
        assert result.value == Decimal("6000")

    def test_mul_token1_times_price_returns_token0(self) -> None:
        # TOKEN1 * PRICE_T1_T0 → TOKEN0
        result = token1("3") * price_t1_t0("2000")
        assert result.denom == "TOKEN0"
        assert result.value == Decimal("6000")

    def test_mul_usd_times_ratio_returns_usd(self) -> None:
        result = usd("1000") * ratio("0.5")
        assert result.denom == "USD"
        assert result.value == Decimal("500")

    def test_mul_unknown_cross_denom_raises(self) -> None:
        with pytest.raises(DenominationError, match="No multiplication rule"):
            usd("10") * token0("5")

    def test_div_same_denom_returns_ratio(self) -> None:
        result = usd("60") / usd("20")
        assert result.denom == "RATIO"
        assert result.value == Decimal("3")

    def test_div_different_denom_raises(self) -> None:
        with pytest.raises(DenominationError):
            token0("100") / token1("5")

    def test_div_by_zero_raises(self) -> None:
        with pytest.raises(ZeroDivisionError):
            usd("10") / usd("0")


# ── TestTaggedDecimalComparisons ─────────────────────────────────────────────

class TestTaggedDecimalComparisons:
    def test_lt_same_denom(self) -> None:
        assert (usd("5") < usd("10")) is True
        assert (usd("10") < usd("5")) is False

    def test_lt_different_denom_raises(self) -> None:
        with pytest.raises(DenominationError):
            usd("5") < token0("10")

    def test_eq_same_value_same_denom(self) -> None:
        assert (usd("42") == usd("42")) is True

    def test_eq_same_value_different_denom_false(self) -> None:
        assert (usd("42") == token0("42")) is False

    def test_neg_preserves_denom(self) -> None:
        t = -usd("10")
        assert t.value == Decimal("-10")
        assert t.denom == "USD"

    def test_abs_preserves_denom(self) -> None:
        t = abs(TaggedDecimal(Decimal("-7"), "TOKEN0"))
        assert t.value == Decimal("7")
        assert t.denom == "TOKEN0"


# ── TestTaggedDecimalConversion ──────────────────────────────────────────────

class TestTaggedDecimalConversion:
    def test_to_converts_value_correctly(self) -> None:
        t = token1("3")
        result = t.to("USD", lambda v: v * Decimal("2000"))
        assert result.value == Decimal("6000")

    def test_to_changes_denom(self) -> None:
        t = token1("3")
        result = t.to("USD", lambda v: v * Decimal("2000"))
        assert result.denom == "USD"

    def test_str_includes_value_and_denom(self) -> None:
        t = usd("42.5")
        assert "42.5" in str(t)
        assert "USD" in str(t)


# ── TestConvenienceConstructors ──────────────────────────────────────────────

class TestConvenienceConstructors:
    def test_usd_constructor(self) -> None:
        t = usd("100")
        assert t.value == Decimal("100")
        assert t.denom == "USD"

    def test_bps_constructor(self) -> None:
        t = bps("30")
        assert t.value == Decimal("30")
        assert t.denom == "BPS"

    def test_price_t1_t0_constructor(self) -> None:
        t = price_t1_t0("2500.50")
        assert t.value == Decimal("2500.50")
        assert t.denom == "PRICE_T1_T0"

    def test_ratio_constructor(self) -> None:
        t = ratio("0.123")
        assert t.value == Decimal("0.123")
        assert t.denom == "RATIO"