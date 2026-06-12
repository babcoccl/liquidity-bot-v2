"""
price_features.py — Token-level feature computation from price DataFrames.

Consumes DataFrames produced by data.loader.price_loader.load_token() /
load_all(). Computes rolling volatility, log returns, momentum signals,
and volume momentum from the float64 price_usd / volume_usd columns.

All intermediate math uses float64 (pandas native). Output columns are
float64. No Decimal in this module — DataFrames are already at the
display/analysis boundary established by price_loader.

Output contract (compute_features return DataFrame):
  Index  : same DatetimeIndex UTC as input, same rows
  Columns (all float64, NaN for insufficient window):
    returns_1h        — log return over 1 period (hourly)
    returns_24h       — log return over 24 periods (rolling window)
    vol_24h           — rolling 24h annualized volatility of log returns
    vol_168h          — rolling 168h (7d) annualized volatility of log returns
    momentum_24h      — price_usd / price_usd.shift(24) - 1
    momentum_168h     — price_usd / price_usd.shift(168) - 1
    vol_momentum_24h  — volume_usd / volume_usd.rolling(24).mean() - 1

# AUDIT:status=complete
# AUDIT:sprint=35
"""

import logging
import math

import pandas as pd

logger = logging.getLogger(__name__)


_HOURS_PER_YEAR: float = 8760.0


def _log_returns(series: pd.Series) -> pd.Series:
    """Compute period-over-period log returns for a price series.

    Uses math.log via pandas apply to match the convention in
    core/metrics.annualized_vol_30d. Returns NaN for first element
    and any row where ratio is non-positive.
    """
    shifted = series.shift(1)
    ratio = series / shifted
    # Guard: log of non-positive is undefined; map to NaN
    return ratio.apply(
        lambda r: math.log(r) if (r is not None and not math.isnan(r) and r > 0) else float("nan")
    )


def _rolling_annualized_vol(log_ret: pd.Series, window: int) -> pd.Series:
    """Rolling annualized volatility from log returns.

    std uses ddof=1 (pandas default). Annualized by sqrt(hours_per_year).
    Returns NaN for windows with fewer than 2 non-NaN observations.
    """
    return log_ret.rolling(window=window, min_periods=2).std() * math.sqrt(_HOURS_PER_YEAR)


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling price and volume features for a single token DataFrame.

    Args:
        df: DataFrame from load_token() — DatetimeIndex UTC, columns include
            price_usd (float64) and volume_usd (float64).

    Returns:
        DataFrame with same index as input. Contains only the feature columns
        listed in the module docstring. Original columns (price_usd, etc.) are
        NOT included in the output — caller joins on index if needed.

    Raises:
        ValueError: If df is empty or missing required columns price_usd /
                    volume_usd.
    """
    if df.empty:
        raise ValueError("compute_features received empty DataFrame")
    for col in ("price_usd", "volume_usd"):
        if col not in df.columns:
            raise ValueError(f"compute_features: required column '{col}' missing")

    price = df["price_usd"]
    volume = df["volume_usd"]

    lr = _log_returns(price)

    out = pd.DataFrame(index=df.index)
    out["returns_1h"]       = lr
    out["returns_24h"]      = price / price.shift(24) - 1     # simple return, not log
    out["vol_24h"]          = _rolling_annualized_vol(lr, window=24)
    out["vol_168h"]         = _rolling_annualized_vol(lr, window=168)
    out["momentum_24h"]     = price / price.shift(24) - 1
    out["momentum_168h"]    = price / price.shift(168) - 1
    out["vol_momentum_24h"] = volume / volume.rolling(window=24, min_periods=1).mean() - 1

    # Enforce float64 dtypes on all columns
    for col in out.columns:
        out[col] = out[col].astype("float64")

    nan_count = out["vol_24h"].isna().sum()
    logger.debug(
        "compute_features: %d rows, %d NaN in vol_24h (window warmup expected)",
        len(out), nan_count
    )

    return out