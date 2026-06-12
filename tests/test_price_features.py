import math
import pandas as pd
import pytest
from data.features.price_features import compute_features


# ── Fixture factory ─────────────────────────────────────────────────────────

def _make_df(
    n: int = 48,
    base_price: float = 1000.0,
    price_step: float = 1.0,
    base_volume: float = 1_000_000.0,
    base_ts: int = 1_700_000_000,
) -> pd.DataFrame:
    """Build a minimal valid load_token()-style DataFrame.

    Prices are linearly increasing: base_price + i * price_step.
    Volumes are constant at base_volume.
    Index is UTC DatetimeIndex named 'datetime', hourly spacing.
    """
    timestamps = [base_ts + i * 3600 for i in range(n)]
    prices = [base_price + i * price_step for i in range(n)]
    volumes = [base_volume] * n
    idx = pd.to_datetime(timestamps, unit="s", utc=True)
    idx.name = "datetime"
    return pd.DataFrame(
        {"symbol": "TEST", "price_usd": prices, "volume_usd": volumes,
         "market_cap_usd": 0.0, "source": "coingecko"},
        index=idx,
    ).astype({"price_usd": "float64", "volume_usd": "float64"})


# ── Tests ───────────────────────────────────────────────────────────────────

def test_compute_features_returns_dataframe():
    df = _make_df(48)
    result = compute_features(df)
    assert isinstance(result, pd.DataFrame)


def test_output_index_matches_input():
    df = _make_df(48)
    result = compute_features(df)
    assert result.index.equals(df.index)


def test_output_columns_exact():
    df = _make_df(48)
    result = compute_features(df)
    expected = {
        "returns_1h", "returns_24h", "vol_24h", "vol_168h",
        "momentum_24h", "momentum_168h", "vol_momentum_24h"
    }
    assert set(result.columns) == expected


def test_all_output_dtypes_float64():
    df = _make_df(48)
    result = compute_features(df)
    for col in result.columns:
        assert result[col].dtype == "float64", f"{col} is {result[col].dtype}, expected float64"


def test_original_columns_not_in_output():
    df = _make_df(48)
    result = compute_features(df)
    assert "price_usd" not in result.columns
    assert "volume_usd" not in result.columns


def test_returns_1h_first_row_nan():
    df = _make_df(48)
    result = compute_features(df)
    assert math.isnan(result["returns_1h"].iloc[0])


def test_returns_1h_correctness():
    df = _make_df(n=48, base_price=1000.0, price_step=10.0)
    result = compute_features(df)
    expected = math.log(1010.0 / 1000.0)
    assert abs(result["returns_1h"].iloc[1] - expected) < 1e-10


def test_vol_24h_nan_warmup():
    df = _make_df(n=48)
    result = compute_features(df)
    # Row 0: NaN (no prior row for log return)
    assert math.isnan(result["vol_24h"].iloc[0])
    # Row 1: NaN (only 1 valid lr in window, min_periods=2)
    assert math.isnan(result["vol_24h"].iloc[1])
    # Row 2: first non-NaN (2 valid lr values: rows 1 and 2)
    assert not math.isnan(result["vol_24h"].iloc[2])


def test_vol_168h_nan_until_row_168():
    df = _make_df(n=200)
    result = compute_features(df)
    # Row 1: NaN (insufficient window)
    assert math.isnan(result["vol_168h"].iloc[1]) is True
    # Row 168: should have enough data for a value
    assert not math.isnan(result["vol_168h"].iloc[168])


def test_momentum_24h_nan_for_first_24_rows():
    df = _make_df(n=48)
    result = compute_features(df)
    assert result["momentum_24h"].iloc[:24].isna().all()


def test_momentum_24h_correctness():
    df = _make_df(n=48, base_price=1000.0, price_step=10.0)
    result = compute_features(df)
    expected = (1000.0 + 24 * 10) / (1000.0 + 0 * 10) - 1  # 1240/1000 - 1 = 0.24
    assert abs(result["momentum_24h"].iloc[24] - expected) < 1e-10


def test_momentum_168h_nan_for_first_168_rows():
    df = _make_df(n=200)
    result = compute_features(df)
    assert result["momentum_168h"].iloc[:168].isna().all()


def test_vol_momentum_24h_no_nan_after_row_0():
    # Constant volume → vol_momentum should be 0.0 everywhere
    df = _make_df(n=48, base_volume=1_000_000.0)
    result = compute_features(df)
    assert (result["vol_momentum_24h"].dropna() == 0.0).all()


def test_raises_on_empty_dataframe():
    with pytest.raises(ValueError):
        compute_features(pd.DataFrame())


def test_raises_on_missing_price_usd():
    df = _make_df(48)
    del df["price_usd"]
    with pytest.raises(ValueError):
        compute_features(df)


def test_raises_on_missing_volume_usd():
    df = _make_df(48)
    del df["volume_usd"]
    with pytest.raises(ValueError):
        compute_features(df)