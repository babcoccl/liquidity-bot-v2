"""Shared pytest fixtures for liquidity-bot-v2 test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def config_dir() -> Path:
    """Return path to the config directory."""
    return Path(__file__).parent.parent / "config"


@pytest.fixture
def default_config(config_dir: Path) -> dict[str, Any]:
    """Load the default.yaml configuration as a dict."""
    import yaml

    cfg_path = config_dir / "default.yaml"
    return yaml.safe_load(cfg_path.read_text())


@pytest.fixture
def sample_pool_data() -> dict[str, Any]:
    """Return a minimal pool data dict for unit tests."""
    return {
        "pool_id": "0xabc123",
        "token_a": "0xWETH",
        "token_b": "0xUSDC",
        "fee_rate": 0.0005,
        "tvl": 5_000_000.0,
        "volume_24h": 1_000_000.0,
    }


@pytest.fixture
def sample_position() -> dict[str, Any]:
    """Return a minimal position dict for unit tests."""
    return {
        "position_id": 1,
        "pool_id": "0xabc123",
        "tick_lower": -887220,
        "tick_upper": -885120,
        "liquidity": 10_000.0,
        "fees_owed_a": 0.0,
        "fees_owed_b": 0.0,
    }


@pytest.fixture
def sample_price_series() -> list[float]:
    """Return a simple price series for IL and backtest tests."""
    return [100.0, 102.0, 98.0, 105.0, 103.0, 110.0, 107.0, 112.0]


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with expected subdirectories."""
    historical = tmp_path / "historical"
    historical.mkdir()
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "registry.json").write_text("[]")
    return tmp_path


@pytest.fixture
def mock_equity_curve() -> list[float]:
    """Return a deterministic equity curve for report tests."""
    base = 10_000.0
    return [base * (1 + 0.01 * i) for i in range(20)]


@pytest.fixture
def mock_backtest_summary(mock_equity_curve: list[float]) -> dict[str, Any]:
    """Return a summary dict that matches MultiPoolBacktest.summary schema."""
    final = mock_equity_curve[-1]
    initial = mock_equity_curve[0]
    return {
        "initial_capital": initial,
        "final_value": final,
        "total_pnl": final - initial,
        "pnl_pct": (final / initial - 1) * 100,
        "max_drawdown": 0.02,
        "active_positions_at_end": 3,
    }


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch):
    """Prevent accidental network calls during tests."""
    import socket

    def fake_connect(*args, **kwargs):
        raise ConnectionError("Network calls are blocked in tests")

    monkeypatch.setattr(socket, "socket", type("FakeSocket", (), {"connect": fake_connect}))