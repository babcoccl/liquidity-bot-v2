"""
Denomination-aware decimal type for all financial quantities.

TaggedDecimal wraps a Decimal with a denomination string.
Arithmetic between incompatible denominations raises DenominationError.
Conversions between denominations are always explicit via .to().

Denomination conventions (authoritative list):
  "USD"          — US dollar value
  "TOKEN0"       — amount in token0 units (human-scale, post-decimal adjustment)
  "TOKEN1"       — amount in token1 units
  "PRICE_T1_T0"  — price: token0 per 1 token1  (token1Price from The Graph)
  "PRICE_T0_T1"  — price: token1 per 1 token0  (token0Price from The Graph)
  "BPS"          — basis points (fee tier; 100 BPS = 1%)
  "RATIO"        — dimensionless ratio (LP share, APR, percentage as decimal)
  "RAW_Q128"     — raw uint256 Q128 fixed-point (fee_growth_global fields)
"""
# AUDIT:status=complete
# AUDIT:sprint=7

from __future__ import annotations
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

logger = logging.getLogger(__name__)


class DenominationError(Exception):
    """Raised when incompatible denominations are combined without explicit conversion."""


MULTIPLY_RULES: dict[tuple[str, str], str] = {
    ("PRICE_T1_T0", "TOKEN1"): "TOKEN0",
    ("TOKEN1", "PRICE_T1_T0"): "TOKEN0",
    ("PRICE_T0_T1", "TOKEN0"): "TOKEN1",
    ("TOKEN0", "PRICE_T0_T1"): "TOKEN1",
    ("USD", "RATIO"):          "USD",
    ("RATIO", "USD"):          "USD",
    ("BPS", "RATIO"):          "RATIO",
    ("RATIO", "BPS"):          "RATIO",
}


@dataclass(frozen=True)
class TaggedDecimal:
    value: Decimal
    denom: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            object.__setattr__(self, "value", Decimal(str(self.value)))
        if not self.denom:
            raise DenominationError("denom must be a non-empty string")

    # Arithmetic — same denomination only
    def __add__(self, other: "TaggedDecimal") -> "TaggedDecimal":
        self._assert_same_denom(other, "+")
        return TaggedDecimal(self.value + other.value, self.denom)

    def __sub__(self, other: "TaggedDecimal") -> "TaggedDecimal":
        self._assert_same_denom(other, "-")
        return TaggedDecimal(self.value - other.value, self.denom)

    # Multiplication — uses MULTIPLY_RULES; falls back to RATIO for same-denom
    def __mul__(self, other: "TaggedDecimal") -> "TaggedDecimal":
        key = (self.denom, other.denom)
        if key in MULTIPLY_RULES:
            return TaggedDecimal(self.value * other.value, MULTIPLY_RULES[key])
        if self.denom == other.denom:
            # Same-denom multiply produces RATIO (e.g. share calculation)
            return TaggedDecimal(self.value * other.value, "RATIO")
        raise DenominationError(
            f"No multiplication rule for ({self.denom}) * ({other.denom}). "
            f"Add to MULTIPLY_RULES or use .to() for explicit conversion."
        )

    # Division — same denomination produces RATIO; cross-denom raises
    def __truediv__(self, other: "TaggedDecimal") -> "TaggedDecimal":
        if other.value == Decimal("0"):
            raise ZeroDivisionError("TaggedDecimal division by zero")
        if self.denom == other.denom:
            return TaggedDecimal(self.value / other.value, "RATIO")
        raise DenominationError(
            f"Cannot divide ({self.denom}) by ({other.denom}) without explicit conversion."
        )

    # Comparisons — same denomination only
    def __lt__(self, other: "TaggedDecimal") -> bool:
        self._assert_same_denom(other, "<")
        return self.value < other.value

    def __le__(self, other: "TaggedDecimal") -> bool:
        self._assert_same_denom(other, "<=")
        return self.value <= other.value

    def __gt__(self, other: "TaggedDecimal") -> bool:
        self._assert_same_denom(other, ">")
        return self.value > other.value

    def __ge__(self, other: "TaggedDecimal") -> bool:
        self._assert_same_denom(other, ">=")
        return self.value >= other.value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaggedDecimal):
            return NotImplemented
        return self.denom == other.denom and self.value == other.value

    def __neg__(self) -> "TaggedDecimal":
        return TaggedDecimal(-self.value, self.denom)

    def __abs__(self) -> "TaggedDecimal":
        return TaggedDecimal(abs(self.value), self.denom)

    def __str__(self) -> str:
        return f"{self.value} {self.denom}"

    def __repr__(self) -> str:
        return f"TaggedDecimal({self.value!r}, {self.denom!r})"

    # Explicit conversion
    def to(self, new_denom: str, converter: "Callable[[Decimal], Decimal]") -> "TaggedDecimal":
        """
        Explicitly convert to a new denomination using a converter function.
        The converter receives self.value and must return a Decimal.
        Logs the conversion at DEBUG level.
        """
        new_value = converter(self.value)
        logger.debug(
            "TaggedDecimal conversion: %s %s → %s %s",
            self.value, self.denom, new_value, new_denom
        )
        return TaggedDecimal(new_value, new_denom)

    # Internal helpers
    def _assert_same_denom(self, other: "TaggedDecimal", op: str) -> None:
        if self.denom != other.denom:
            raise DenominationError(
                f"Cannot apply '{op}' between denomination '{self.denom}' "
                f"and '{other.denom}'. Use .to() for explicit conversion."
            )


# Convenience constructors

def usd(value: Decimal | str | int | float) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "USD")


def token0(value: Decimal | str | int | float) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "TOKEN0")


def token1(value: Decimal | str | int | float) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "TOKEN1")


def price_t1_t0(value: Decimal | str | int | float) -> TaggedDecimal:
    """token1Price from The Graph — token0 per 1 token1."""
    return TaggedDecimal(Decimal(str(value)), "PRICE_T1_T0")


def price_t0_t1(value: Decimal | str | int | float) -> TaggedDecimal:
    """token0Price from The Graph — token1 per 1 token0."""
    return TaggedDecimal(Decimal(str(value)), "PRICE_T0_T1")


def bps(value: Decimal | str | int | float) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "BPS")


def ratio(value: Decimal | str | int | float) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "RATIO")


def raw_q128(value: int) -> TaggedDecimal:
    return TaggedDecimal(Decimal(str(value)), "RAW_Q128")