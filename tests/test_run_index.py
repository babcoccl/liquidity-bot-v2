"""TEST run_index module. USE TMP_PATH. NEVER WRITE TO results/ IN TESTS."""
# AUDIT:status=complete
# AUDIT:sprint=20

import pytest
from decimal import Decimal
from pathlib import Path

from reporting.run_index import RunIndex, RunIndexEntry
from backtest.config import BacktestConfig


@pytest.fixture
def temp_index_path(tmp_path):
    """RETURN TEMP PATH FOR INDEX FILE."""
    p = tmp_path / "run_index.json"
    return p


@pytest.fixture
def entry():
    """RETURN ONE SAMPLE ENTRY."""
    return RunIndexEntry(
        run_id="20260607_201500_a3f9c1",
        timestamp="2026-06-07T20:15:00Z",
        config_hash="a3f9c1",
        pools_evaluated=15,
        pools_simulated=11,
        pools_skipped_entry_gate=4,
        mean_net_lp_alpha=Decimal("0.0312"),
        mean_fee_apr=Decimal("0.184"),
        most_common_exit_reason="IL_EXCEEDED",
    )


@pytest.fixture
def config():
    """RETURN BACKTEST CONFIG."""
    return BacktestConfig(
        days=90,
        initial_capital=Decimal("10000"),
        bollinger_multiplier=2.0,
        rotation_margin=Decimal("0.05"),
        min_entry_score=Decimal("0.25"),
        rebalance_cooldown_hours=6,
        max_rebalances_per_pool_per_day=4,
        historical_dir="data/historical",
        registry_path="registry/registry.json",
        prices_dir="data/prices",
        hourly_dir="data/hourly",
        max_il_pct=Decimal("-0.05"),
        min_tvl_usd=Decimal("500000"),
        min_volume_usd=Decimal("50000"),
        max_hold_hours=720,
        metrics_window_hours=720,
    )


def _monkeypatch_index(idx: RunIndex, path: Path):
    """MONKEYPATCH INDEX_PATH ON INSTANCE."""
    idx.INDEX_PATH = path


# ---------- append / load tests ----------

def test_run_index_append_creates_file(temp_index_path, entry):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    idx.append(entry)
    assert temp_index_path.exists()
    data = idx.load()
    assert len(data) == 1


def test_run_index_append_is_additive(temp_index_path, entry):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    idx.append(entry)
    e2 = RunIndexEntry(
        run_id="run_002", timestamp="2026-06-08T10:00:00Z", config_hash="bbbbbb",
        pools_evaluated=10, pools_simulated=8, pools_skipped_entry_gate=2,
        mean_net_lp_alpha=Decimal("0.05"), mean_fee_apr=Decimal("0.20"),
        most_common_exit_reason="MAX_HOLD_EXCEEDED",
    )
    idx.append(e2)
    data = idx.load()
    assert len(data) == 2


def test_run_index_load_empty_if_missing(temp_index_path):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    result = idx.load()
    assert result == []


def test_run_index_load_deserializes_decimal_fields(temp_index_path, entry):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    idx.append(entry)
    loaded = idx.load()
    assert len(loaded) == 1
    e = loaded[0]
    assert isinstance(e.mean_net_lp_alpha, Decimal)
    assert e.mean_net_lp_alpha == Decimal("0.0312")


# ---------- latest tests ----------

def test_run_index_latest_returns_last_n(temp_index_path):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    for i in range(5):
        idx.append(RunIndexEntry(
            run_id=f"run_{i:03d}", timestamp=f"2026-06-{i+1:02d}T10:00:00Z",
            config_hash="aaaaaa", pools_evaluated=5, pools_simulated=4,
            pools_skipped_entry_gate=1, mean_net_lp_alpha=Decimal("0.03"),
            mean_fee_apr=Decimal("0.18"), most_common_exit_reason="IL_EXCEEDED",
        ))
    latest = idx.latest(3)
    assert len(latest) == 3
    # CHRONOLOGICAL ORDER (ASCENDING)
    assert latest[0].timestamp < latest[1].timestamp < latest[2].timestamp


def test_run_index_latest_returns_all_if_fewer_than_n(temp_index_path):
    idx = RunIndex()
    _monkeypatch_index(idx, temp_index_path)
    for i in range(2):
        idx.append(RunIndexEntry(
            run_id=f"run_{i:03d}", timestamp=f"2026-06-{i+1:02d}T10:00:00Z",
            config_hash="aaaaaa", pools_evaluated=5, pools_simulated=4,
            pools_skipped_entry_gate=1, mean_net_lp_alpha=Decimal("0.03"),
            mean_fee_apr=Decimal("0.18"), most_common_exit_reason="IL_EXCEEDED",
        ))
    latest = idx.latest(10)
    assert len(latest) == 2


# ---------- config_hash tests ----------

def test_config_hash_is_six_chars(config):
    h = RunIndex.config_hash_from_config(config)
    assert len(h) == 6
    int(h, 16)  # MUST BE VALID HEX


def test_config_hash_same_config_same_hash(config):
    h1 = RunIndex.config_hash_from_config(config)
    h2 = RunIndex.config_hash_from_config(config)
    assert h1 == h2


def test_config_hash_different_config_different_hash(config):
    config2 = BacktestConfig(
        days=30,  # DIFFERENT FROM DEFAULT 90
        initial_capital=Decimal("10000"),
        bollinger_multiplier=2.0,
        rotation_margin=Decimal("0.05"),
        min_entry_score=Decimal("0.25"),
        rebalance_cooldown_hours=6,
        max_rebalances_per_pool_per_day=4,
        historical_dir="data/historical",
        registry_path="registry/registry.json",
        prices_dir="data/prices",
        hourly_dir="data/hourly",
        max_il_pct=Decimal("-0.05"),
        min_tvl_usd=Decimal("500000"),
        min_volume_usd=Decimal("50000"),
        max_hold_hours=720,
        metrics_window_hours=720,
    )
    h1 = RunIndex.config_hash_from_config(config)
    h2 = RunIndex.config_hash_from_config(config2)
    assert h1 != h2