"""
price_loader.py — Load data/prices/{SYMBOL}.json files into pandas DataFrames.

Analysis-layer loader. Separate concern from token_price_loader.py,
which handles domain-model (TokenHistoryPoint) serialization.

# AUDIT:status=complete
# AUDIT:sprint=34-loader
"""

import json
import logging
from decimal import Decimal
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def load_token(symbol: str, data_dir: str | Path = "data/prices") -> pd.DataFrame:
    """Load a single token's price history JSON into a pandas DataFrame.

    Args:
        symbol: Token symbol (e.g. "WETH"). Must match filename exactly
                (case-sensitive, no normalization).
        data_dir: Directory containing {SYMBOL}.json files.

    Returns:
        DataFrame with columns ["symbol", "price_usd", "volume_usd",
        "market_cap_usd", "source"], indexed by UTC datetime.

    Raises:
        FileNotFoundError: If price file does not exist.
        ValueError: If JSON is malformed or has no records.
    """
    path = Path(data_dir) / f"{symbol}.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Price file not found for {symbol}: {path}"
        )

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed JSON for {symbol}: {e}")

    records = data.get("records")
    if not records:
        raise ValueError(f"No records in price file for {symbol}")

    # Build DataFrame from records list
    df = pd.DataFrame(records)

    # Drop rows where price_usd is null/missing, log per dropped row
    null_price_mask = df["price_usd"].isna() | (df["price_usd"] == "")
    dropped_count = null_price_mask.sum()
    if dropped_count > 0:
        for idx in df[null_price_mask].index:
            ts = df.loc[idx, "timestamp"]
            logger.warning(
                "Dropping record at timestamp %s for %s: missing price_usd",
                ts,
                symbol,
            )
        df = df[~null_price_mask]

    # Cast financial columns: Decimal string → float64 (float permitted at analysis boundary)
    df["price_usd"] = df["price_usd"].apply(lambda v: float(Decimal(str(v)))).astype("float64")
    df["volume_usd"] = df["volume_usd"].apply(lambda v: float(Decimal(str(v)))).astype("float64")

    # market_cap_usd: coerce nulls to NaN, not zero
    df["market_cap_usd"] = df["market_cap_usd"].apply(
        lambda v: float(Decimal(str(v))) if v is not None and v != "" else float("nan")
    ).astype("float64")

    # timestamp → int64
    df["timestamp"] = df["timestamp"].astype("int64")

    # Convert Unix seconds → UTC datetime
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)

    # Set datetime as index, drop raw timestamp
    df = df.set_index("datetime")
    df.index.name = "datetime"
    df = df.drop(columns=["timestamp"])

    # Add symbol column
    df["symbol"] = symbol

    # Sort index ascending
    df = df.sort_index()

    # Return with canonical column order
    return df[["symbol", "price_usd", "volume_usd", "market_cap_usd", "source"]]


def load_all(
    data_dir: str | Path = "data/prices",
    min_records: int = 0,
) -> dict[str, pd.DataFrame]:
    """Load all token price JSON files from a directory.

    Args:
        data_dir: Directory containing {SYMBOL}.json files.
        min_records: If > 0, skip tokens with fewer records than this threshold.

    Returns:
        Dict mapping symbol → DataFrame.
    """
    data_path = Path(data_dir)
    result: dict[str, pd.DataFrame] = {}

    for path in sorted(data_path.glob("*.json")):
        # Skip .gitkeep or non-json files
        if path.name == ".gitkeep" or not path.name.endswith(".json"):
            continue

        symbol = path.stem  # e.g. WETH.json → "WETH"

        try:
            df = load_token(symbol, data_dir)
        except (FileNotFoundError, ValueError) as e:
            logger.warning("Skipping %s: %s", symbol, e)
            continue

        if min_records > 0 and len(df) < min_records:
            logger.warning(
                "Skipping %s: only %d records (min_records=%d)",
                symbol,
                len(df),
                min_records,
            )
            continue

        result[symbol] = df

    logger.info("Loaded %d tokens from %s", len(result), data_dir)
    return result


def get_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Resample hourly price DataFrame to daily OHLCV candles.

    Args:
        df: DataFrame from load_token() with UTC datetime index.

    Returns:
        Daily-resampled DataFrame with columns:
        ["symbol", "price_open", "price_high", "price_low",
         "price_close", "volume_usd", "market_cap_usd"].
    """
    # Carry forward symbol before resampling
    symbol_value = df["symbol"].iloc[0] if len(df) > 0 else None

    # Drop symbol from resample source (it's constant per token)
    if "symbol" in df.columns:
        df_price = df.drop(columns=["symbol"])
    else:
        df_price = df.copy()

    # Resample to daily, UTC calendar day
    resampled = df_price.resample("1D")

    # OHLCV aggregations on price_usd
    price_open = resampled["price_usd"].first()
    price_high = resampled["price_usd"].max()
    price_low = resampled["price_usd"].min()
    price_close = resampled["price_usd"].last()

    # Volume sums, market cap last
    volume_usd = resampled["volume_usd"].sum()
    market_cap_usd = resampled["market_cap_usd"].last()

    daily = pd.DataFrame({
        "price_open": price_open,
        "price_high": price_high,
        "price_low": price_low,
        "price_close": price_close,
        "volume_usd": volume_usd,
        "market_cap_usd": market_cap_usd,
    })

    # Re-attach symbol column
    daily["symbol"] = symbol_value

    # Drop days where price_open is NaN (incomplete candles)
    daily = daily.dropna(subset=["price_open"])

    return daily[["symbol", "price_open", "price_high", "price_low", "price_close", "volume_usd", "market_cap_usd"]]