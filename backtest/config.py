"""
BacktestConfig — typed configuration for backtest runs.
Loaded from config/default.yaml backtest section.
All financial values stored as Decimal.

# AUDIT:status=complete
# AUDIT:sprint=12
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import yaml


@dataclass(frozen=True)
class BacktestConfig:
    days: int
    initial_capital: Decimal
    bollinger_multiplier: Decimal
    rotation_margin: Decimal
    min_entry_score: Decimal
    rebalance_cooldown_hours: Decimal
    max_rebalances_per_pool_per_day: int
    historical_dir: Path
    registry_path: Path
    prices_dir: Path = Path("data/prices")
    hourly_dir: Path = Path("data/historical")
    max_il_pct: Decimal = Decimal("-0.05")
    min_tvl_usd: Decimal = Decimal("500000")
    min_volume_usd: Decimal = Decimal("50000")
    max_hold_hours: int = 720

    @classmethod
    def from_yaml(cls, path: Path = Path("config/default.yaml")) -> "BacktestConfig":
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
        bt = cfg["backtest"]
        return cls(
            days=int(bt.get("days", 365)),
            initial_capital=Decimal(str(bt.get("initial_capital", "10000"))),
            bollinger_multiplier=Decimal(str(bt.get("bollinger_multiplier", "2"))),
            rotation_margin=Decimal(str(bt.get("rotation_margin", "0.01"))),
            min_entry_score=Decimal(str(bt.get("min_entry_score", "0"))),
            rebalance_cooldown_hours=Decimal(str(bt.get("rebalance_cooldown_hours", "0"))),
            max_rebalances_per_pool_per_day=int(bt.get("max_rebalances_per_pool_per_day", 99)),
            historical_dir=Path(bt.get("historical_dir", "data/historical")),
            registry_path=Path(bt.get("registry_path", "registry/registry.json")),
            prices_dir=Path(bt.get("prices_dir", "data/prices")),
            hourly_dir=Path(bt.get("hourly_dir", "data/historical")),
            max_il_pct=Decimal(str(bt.get("max_il_pct", "-0.05"))),
            min_tvl_usd=Decimal(str(bt.get("min_tvl_usd", "500000"))),
            min_volume_usd=Decimal(str(bt.get("min_volume_usd", "50000"))),
            max_hold_hours=int(bt.get("max_hold_hours", 720)),
        )
