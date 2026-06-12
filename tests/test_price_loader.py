"""
tests/test_price_loader.py — Tests for data/loader/price_loader.py

# AUDIT:status=complete
# AUDIT:sprint=34-loader
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from data.loader.price_loader import get_daily, load_all, load_token


def _make_price_file(tmp_path: Path, symbol: str, n_records: int = 48) -> Path:
    """Write a minimal valid price JSON file with n_records hourly entries."""
    base_ts = 1773435600
    records = [
        {
            "timestamp": base_ts + i * 3600,
            "price_usd": str(2000 + i * 0.5),
            "volume_usd": str(1_000_000 + i * 500),
            "market_cap_usd": str(4_500_000_000 + i * 1000),
            "source": "coingecko",
        }
        for i in range(n_records)
    ]
    payload = {
        "token_address": "0x4200000000000000000000000000000000000006",
        "symbol": symbol,
        "fetched_at": base_ts + n_records * 3600,
        "records": records,
    }
    path = tmp_path / f"{symbol}.json"
    path.write_text(json.dumps(payload))
    return path


# ─────────────────────────────────────────────
# load_token tests
# ─────────────────────────────────────────────

def test_load_token_returns_dataframe(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)
    df = load_token("WETH", data_dir=tmp_path)

    assert isinstance(df, pd.DataFrame)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.tz is not None  # UTC


def test_load_token_column_dtypes(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)
    df = load_token("WETH", data_dir=tmp_path)

    assert df["price_usd"].dtype == "float64"
    assert df["volume_usd"].dtype == "float64"
    assert df["market_cap_usd"].dtype == "float64"
    assert df["symbol"].dtype == "string"


def test_load_token_sorted_ascending(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)
    df = load_token("WETH", data_dir=tmp_path)

    assert df.index.is_monotonic_increasing


def test_load_token_symbol_column(tmp_path: Path):
    _make_price_file(tmp_path, "TESTTKN", n_records=24)
    df = load_token("TESTTKN", data_dir=tmp_path)

    assert (df["symbol"] == "TESTTKN").all()


def test_load_token_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="Price file not found"):
        load_token("NONEXISTENT", data_dir=tmp_path)


def test_load_token_empty_records(tmp_path: Path):
    payload = {
        "token_address": "0x0",
        "symbol": "EMPTY",
        "fetched_at": 1773435600,
        "records": [],
    }
    (tmp_path / "EMPTY.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="No records"):
        load_token("EMPTY", data_dir=tmp_path)


def test_load_token_missing_records_key(tmp_path: Path):
    payload = {
        "token_address": "0x0",
        "symbol": "NOREC",
        "fetched_at": 1773435600,
    }
    (tmp_path / "NOREC.json").write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="No records"):
        load_token("NOREC", data_dir=tmp_path)


def test_load_token_drops_null_price_rows(tmp_path: Path):
    base_ts = 1773435600
    records = [
        {"timestamp": base_ts, "price_usd": "100.0", "volume_usd": "1000", "market_cap_usd": "10000", "source": "test"},
        {"timestamp": base_ts + 3600, "price_usd": None, "volume_usd": "1000", "market_cap_usd": "10000", "source": "test"},
        {"timestamp": base_ts + 7200, "price_usd": "102.0", "volume_usd": "1000", "market_cap_usd": "10000", "source": "test"},
    ]
    payload = {
        "token_address": "0x0",
        "symbol": "NULLPRC",
        "fetched_at": base_ts + 7200,
        "records": records,
    }
    (tmp_path / "NULLPRC.json").write_text(json.dumps(payload))

    df = load_token("NULLPRC", data_dir=tmp_path)
    assert len(df) == 2
    assert df["price_usd"].iloc[0] == 100.0
    assert df["price_usd"].iloc[1] == 102.0


# ─────────────────────────────────────────────
# load_all tests
# ─────────────────────────────────────────────

def test_load_all_returns_dict(tmp_path: Path):
    _make_price_file(tmp_path, "TOKA", n_records=24)
    _make_price_file(tmp_path, "TOKB", n_records=36)

    result = load_all(data_dir=tmp_path)

    assert isinstance(result, dict)
    assert "TOKA" in result
    assert "TOKB" in result
    for df in result.values():
        assert isinstance(df, pd.DataFrame)


def test_load_all_min_records_filter(tmp_path: Path):
    _make_price_file(tmp_path, "SMALL", n_records=5)
    _make_price_file(tmp_path, "BIG", n_records=100)

    result = load_all(data_dir=tmp_path, min_records=10)

    assert "SMALL" not in result
    assert "BIG" in result


def test_load_all_skips_gitkeep(tmp_path: Path):
    (tmp_path / ".gitkeep").write_text("")
    _make_price_file(tmp_path, "REAL", n_records=24)

    result = load_all(data_dir=tmp_path)

    assert "REAL" in result
    assert ".gitkeep" not in result


# ─────────────────────────────────────────────
# get_daily tests
# ─────────────────────────────────────────────

def test_get_daily_fewer_rows(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)  # 2 full days of hourly data
    df = load_token("WETH", data_dir=tmp_path)
    daily = get_daily(df)

    assert len(daily) < len(df)


def test_get_daily_volume_sum(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)
    df = load_token("WETH", data_dir=tmp_path)
    daily = get_daily(df)

    # First daily row volume should equal sum of hourly volumes for that day
    first_day_idx = daily.index[0].date()
    hourly_volumes_that_day = df[df.index.date == first_day_idx]["volume_usd"]
    daily_volume = daily["volume_usd"].iloc[0]

    assert abs(daily_volume - hourly_volumes_that_day.sum()) < 1e-6


def test_get_daily_price_ohlc(tmp_path: Path):
    _make_price_file(tmp_path, "WETH", n_records=48)
    df = load_token("WETH", data_dir=tmp_path)
    daily = get_daily(df)

    for _, row in daily.iterrows():
        assert row["price_high"] >= row["price_open"]
        assert row["price_high"] >= row["price_close"]
        assert row["price_low"] <= row["price_open"]