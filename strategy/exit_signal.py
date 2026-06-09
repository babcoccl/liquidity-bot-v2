"""
ExitSignal — result of evaluating a position for exit.
ExitReason — enumeration of why an exit was triggered.
"""
# AUDIT:status=complete
# AUDIT:sprint=26

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto


class ExitReason(Enum):
    IL_THRESHOLD        = auto()  # IL exceeded configured max
    PRICE_OUT_OF_RANGE  = auto()  # token price left tick range
    TVL_DECAY           = auto()  # pool TVL dropped below minimum
    VOLUME_DECAY        = auto()  # pool volume dropped below minimum
    TIME_LIMIT          = auto()  # max hold duration exceeded
    TREND_EXIT          = auto()  # trend breakout / adverse move detected
    MANUAL              = auto()  # operator-triggered


@dataclass(frozen=False)
class ExitSignal:
    triggered: bool
    reason: ExitReason | None       # None if triggered=False
    il_current: Decimal             # current IL as negative Decimal
    tvl_current: Decimal = Decimal("0")
    volume_current: Decimal = Decimal("0")
    hours_held: int = 0
    details: str = ""               # human-readable explanation