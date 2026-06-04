"""
ExitSignal — result of evaluating a position for exit.
ExitReason — enumeration of why an exit was triggered.
"""
# AUDIT:status=complete
# AUDIT:sprint=11

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum, auto


class ExitReason(Enum):
    IL_THRESHOLD        = auto()  # IL exceeded configured max
    PRICE_OUT_OF_RANGE  = auto()  # token price left tick range
    TVL_DECAY           = auto()  # pool TVL dropped below minimum
    VOLUME_DECAY        = auto()  # pool volume dropped below minimum
    TIME_LIMIT          = auto()  # max hold duration exceeded
    MANUAL              = auto()  # operator-triggered


@dataclass(frozen=True)
class ExitSignal:
    triggered: bool
    reason: ExitReason | None       # None if triggered=False
    il_current: Decimal             # current IL as negative Decimal
    timestamp: int                  # UTC unix seconds of evaluation
    details: str = ""               # human-readable explanation