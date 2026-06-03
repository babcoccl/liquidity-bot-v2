"""
TokenPriceLoader — save/load TokenHistoryPoint records to data/prices/{SYMBOL}.json.

Wrapper schema:
{
  "token_address": "0x...",
  "symbol": "WETH",
  "fetched_at": 1748908800,
  "records": [
    {
      "timestamp": 1748908800,
      "price_usd": "2541.33",
      "volume_usd": "183421900.12",
      "market_cap_usd": "10482930000.00",
      "source": "coingecko"
    }
  ]
}

# AUDIT:status=complete
# AUDIT:sprint=10
"""

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.models import TokenHistoryPoint

logger = logging.getLogger(__name__)


def _serialize_token_point(record: TokenHistoryPoint) -> dict[str, Any]:
    """Serialize a TokenHistoryPoint to a flat row (token_address/symbol hoisted)."""
    return {
        "timestamp": record.timestamp,
        "price_usd": str(record.price_usd),
        "volume_usd": str(record.volume_usd),
        "market_cap_usd": str(record.market_cap_usd) if record.market_cap_usd is not None else None,
        "source": record.source,
    }


def save_token_prices(
    token_address: str,
    symbol: str,
    records: list[TokenHistoryPoint],
    path: Path,
) -> None:
    """Serialize token price history to JSON with atomic write.

    Wrapper schema hoists token_address and symbol to file root.
    Warns and returns early if records is empty.
    """
    if not records:
        logger.warning("No token price records to save for %s", symbol)
        return

    payload = {
        "token_address": token_address.lower(),
        "symbol": symbol,
        "fetched_at": int(time.time()),
        "records": [_serialize_token_point(r) for r in records],
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = Path(str(path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    tmp_path.rename(path)


def load_token_prices(path: Path) -> list[TokenHistoryPoint]:
    """Load token price history from a JSON file.

    Reconstructs TokenHistoryPoint records from the wrapper schema.
    Injects token_address and symbol from root onto each record.
    Returns records sorted ascending by timestamp.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Token price file not found: {path}")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {path.name}: {e}")

    if not isinstance(data, dict):
        raise ValueError(f"Expected dict wrapper in {path.name}, got {type(data).__name__}")

    token_address = str(data.get("token_address", "")).lower()
    symbol = str(data.get("symbol", ""))

    results: list[TokenHistoryPoint] = []
    for entry in data.get("records", []):
        record = TokenHistoryPoint(
            token_address=token_address,
            symbol=symbol,
            timestamp=int(entry["timestamp"]),
            price_usd=Decimal(str(entry.get("price_usd", "0"))),
            volume_usd=Decimal(str(entry.get("volume_usd", "0"))),
            market_cap_usd=(
                Decimal(str(entry["market_cap_usd"]))
                if entry.get("market_cap_usd") is not None
                else None
            ),
            source=entry.get("source", "coingecko"),
        )
        results.append(record)

    return sorted(results, key=lambda r: r.timestamp)