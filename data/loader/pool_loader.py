"""
PoolLoader — loads pool history from data/historical/*.json files.
Normalizes to list[PoolDayData] or list[PoolHistoryPoint] depending on schema.
Handles both v1 column naming schemas and hourly flat-array format.
"""
# AUDIT:status=complete
# AUDIT:sprint=9-hotfix3

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Union

from core.models import PoolDayData, PoolHistoryPoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column name aliases (camelCase v1 -> snake_case canonical)
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


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _serialize_history_point(record: PoolHistoryPoint) -> dict[str, Any]:
    """Serialize a PoolHistoryPoint to a flat hourly record."""
    return {
        "pool_address": record.pool_address.lower(),
        "timestamp": record.timestamp,
        "price_token1_in_token0": str(record.price_token1_in_token0),
        "price_token0_in_token1": str(record.price_token0_in_token1),
        "volume_usd": str(record.volume_usd),
        "tvl_usd": str(record.tvl_usd),
        "fee_growth_global_0": record.fee_growth_global_0,
        "fee_growth_global_1": record.fee_growth_global_1,
        "source": record.source,
    }


def _serialize_day_data(record: PoolDayData) -> dict[str, Any]:
    """Serialize a PoolDayData to the legacy daily format."""
    return {
        "date": record.date,
        "volumeUSD": str(record.volume_usd),
        "tvlUSD": str(record.tvl_usd),
        "token0Price": str(record.price_token0_in_token1),
        "token1Price": str(record.price_token1_in_token0),
        "feeGrowthGlobal0X128": (
            str(record.fee_growth_global_0) if record.fee_growth_global_0 is not None else None
        ),
        "feeGrowthGlobal1X128": (
            str(record.fee_growth_global_1) if record.fee_growth_global_1 is not None else None
        ),
        "source": record.source,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_pool_history(path: Path) -> Union[list[PoolDayData], list[PoolHistoryPoint]]:
    """Load and normalize pool history from a JSON file.

    Detects format automatically:
    - Flat array with "timestamp" keys -> PoolHistoryPoint (hourly)
    - Wrapper dict with "days" key -> PoolDayData (daily, legacy)
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Historical data file not found: {path}")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {path.name}: {e}")

    # Detect flat hourly array format
    if isinstance(data, list):
        results: list[PoolHistoryPoint] = []
        for entry in data:
            record = PoolHistoryPoint(
                pool_address=str(entry.get("pool_address", "")).lower(),
                timestamp=int(entry["timestamp"]),
                price_token1_in_token0=_parse_decimal(
                    entry.get("price_token1_in_token0", "0")
                ),
                price_token0_in_token1=_parse_decimal(
                    entry.get("price_token0_in_token1", "0")
                ),
                volume_usd=_parse_decimal(entry.get("volume_usd", "0")),
                tvl_usd=_parse_decimal(entry.get("tvl_usd", "0")),
                fee_growth_global_0=_parse_fee_growth(
                    entry.get("fee_growth_global_0")
                ),
                fee_growth_global_1=_parse_fee_growth(
                    entry.get("fee_growth_global_1")
                ),
                source=entry.get("source", "the_graph"),
            )
            results.append(record)
        return sorted(results, key=lambda r: r.timestamp)

    # Legacy daily wrapper format with "days" key
    pool_address = str(data.get("pool_address", "")).lower()
    results_day: list[PoolDayData] = []

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
        results_day.append(record)

    return sorted(results_day, key=lambda r: r.date)


def save_pool_history(
    pool_address: str,
    pair_name: str,
    records: list[Any],
    path: Path,
) -> None:
    """Serialize pool history records to JSON with atomic write.

    Accepts both PoolDayData (daily-bucketed) and PoolHistoryPoint
    (hourly-preserved) records via duck-typing.

    PoolHistoryPoint records are saved as a flat array (new format).
    PoolDayData records use the legacy wrapper dict (backward compat).
    """
    if not records:
        logger.warning("No records to save for %s", pair_name)
        return

    # Detect record type via duck typing
    is_hourly = hasattr(records[0], "timestamp")

    if is_hourly:
        # Serialize as flat array of PoolHistoryPoint records
        serialized = [_serialize_history_point(r) for r in records]
        tmp_path = Path(str(path) + ".tmp")
        with open(tmp_path, "w") as f:
            json.dump(serialized, f, indent=2)
        tmp_path.rename(path)
    else:
        # Legacy PoolDayData format with wrapper dict
        days = [_serialize_day_data(r) for r in records]
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