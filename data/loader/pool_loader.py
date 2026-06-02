"""
PoolLoader — loads pool history from data/historical/*.json files.
Normalizes to list[PoolDayData].
Handles both v1 column naming schemas.
"""
# AUDIT:status=complete
# AUDIT:sprint=1

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.models import PoolDayData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column name aliases (camelCase v1 → snake_case canonical)
# ---------------------------------------------------------------------------
_VOLUME_ALIASES = ("volumeUSD", "volume_usd", "volume")
_TVL_ALIASES = ("tvlUSD", "tvl_usd", "tvl")
_PRICE0_ALIASES = ("token0Price", "token0_price")
_PRICE1_ALIASES = ("token1Price", "token1_price")
_FEE0_ALIASES = ("feeGrowthGlobal0X128", "fee_growth_global_0")
_FEE1_ALIASES = ("feeGrowthGlobal1X128", "fee_growth_global_1")


def _get(entry: dict[str, Any], aliases: tuple[str, ...], default: Any = None) -> Any:
    """Return the first non-None value found under *aliases*."""
    for key in aliases:
        if key in entry:
            return entry[key]
    return default


def _parse_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _parse_fee_growth(value: Any) -> int | None:
    """Parse fee growth as int, returning None for null / 0 / missing."""
    if value is None or value == "0" or value == "" or value == 0:
        return None
    return int(value)


def load_pool_history(path: Path) -> list[PoolDayData]:
    """Load and normalize pool history from a JSON file."""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Historical data file not found: {path}")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {path.name}: {e}")

    # Extract pool address from top-level key
    pool_address = str(data.get("pool_address", "")).lower()

    results: list[PoolDayData] = []

    for day_entry in data.get("days", []):
        volume_usd = _parse_decimal(_get(day_entry, _VOLUME_ALIASES, "0"))
        tvl_usd = _parse_decimal(_get(day_entry, _TVL_ALIASES, "0"))

        # Skip zero rows
        if volume_usd == Decimal("0") and tvl_usd == Decimal("0"):
            logger.warning(
                "Skipping row with zero volume and TVL at date=%s",
                day_entry.get("date"),
            )
            continue

        record = PoolDayData(
            pool_address=pool_address,
            date=int(day_entry["date"]),
            price_token1_in_token0=_parse_decimal(
                _get(day_entry, _PRICE1_ALIASES, "0")
            ),
            price_token0_in_token1=_parse_decimal(
                _get(day_entry, _PRICE0_ALIASES, "0")
            ),
            volume_usd=volume_usd,
            tvl_usd=tvl_usd,
            fee_growth_global_0=_parse_fee_growth(_get(day_entry, _FEE0_ALIASES)),
            fee_growth_global_1=_parse_fee_growth(_get(day_entry, _FEE1_ALIASES)),
            source=day_entry.get("source", "the_graph"),
        )
        results.append(record)

    return sorted(results, key=lambda r: r.date)


def save_pool_history(
    pool_address: str,
    pair_name: str,
    records: list[PoolDayData],
    path: Path,
) -> None:
    """Serialize PoolDayData records to JSON with atomic write."""
    days = []
    for r in records:
        days.append(
            {
                "date": r.date,
                "volumeUSD": str(r.volume_usd),
                "tvlUSD": str(r.tvl_usd),
                "token0Price": str(r.price_token0_in_token1),
                "token1Price": str(r.price_token1_in_token0),
                "feeGrowthGlobal0X128": (
                    str(r.fee_growth_global_0) if r.fee_growth_global_0 is not None else None
                ),
                "feeGrowthGlobal1X128": (
                    str(r.fee_growth_global_1) if r.fee_growth_global_1 is not None else None
                ),
                "source": r.source,
            }
        )

    payload = {
        "pool_address": pool_address.lower(),
        "pair_name": pair_name,
        "fetched_at": int(time.time()),
        "days": days,
    }

    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    tmp_path.rename(path)