"""
TokenLoader — persists token price history to data/token_history/*.json.
Saves TokenHistoryPoint records with atomic writes.
"""
# AUDIT:status=complete
# AUDIT:sprint=9

import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, List

from core.models import TokenHistoryPoint

logger = logging.getLogger(__name__)


def save_token_history(
    token_address: str,
    symbol: str,
    records: List[TokenHistoryPoint],
    output_path: Path | None = None,
) -> Path:
    """Save token history to JSON file.

    Args:
        token_address: lowercase hex address of the token
        symbol: token symbol e.g. "WETH"
        records: sorted list of TokenHistoryPoint records
        output_path: optional override; defaults to data/token_history/<symbol>.json

    Returns:
        The final Path where the file was written.
    """
    if output_path is None:
        base_dir = Path("data/token_history")
        output_path = base_dir / f"{symbol}.json"

    # Create parent directory automatically
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for r in records:
        rows.append(
            {
                "token_address": r.token_address,
                "symbol": r.symbol,
                "timestamp": r.timestamp,
                "price_usd": str(r.price_usd),
                "volume_usd": str(r.volume_usd),
                "market_cap_usd": str(r.market_cap_usd) if r.market_cap_usd is not None else None,
                "source": r.source,
            }
        )

    payload = {
        "token_address": token_address.lower(),
        "symbol": symbol,
        "fetched_at": int(time.time()),
        "points": rows,
    }

    tmp_path = Path(str(output_path) + ".tmp")
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    tmp_path.rename(output_path)

    logger.info(
        "TokenLoader: saved %d points for %s to %s", len(records), symbol, output_path
    )
    return output_path


def load_token_history(path: Path) -> List[TokenHistoryPoint]:
    """Load token history from a JSON file.

    Args:
        path: path to <symbol>.json in data/token_history/

    Returns:
        Sorted list of TokenHistoryPoint records (ascending by timestamp).
    """
    if not path.exists():
        raise FileNotFoundError(f"Token history file not found: {path}")

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON in {path.name}: {e}")

    token_address = str(data.get("token_address", "")).lower()
    symbol = str(data.get("symbol", ""))

    results: list[TokenHistoryPoint] = []
    for entry in data.get("points", []):
        record = TokenHistoryPoint(
            token_address=token_address,
            symbol=symbol,
            timestamp=int(entry["timestamp"]),
            price_usd=Decimal(str(entry["price_usd"])),
            volume_usd=Decimal(str(entry.get("volume_usd", "0"))),
            market_cap_usd=(
                Decimal(str(entry["market_cap_usd"]))
                if entry.get("market_cap_usd") is not None
                else None
            ),
            source=str(entry.get("source", "coingecko")),
        )
        results.append(record)

    return sorted(results, key=lambda r: r.timestamp)