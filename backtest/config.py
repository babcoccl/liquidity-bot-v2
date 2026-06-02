"""
BacktestConfig — typed configuration for backtest runs.
Loaded from config/default.yaml backtest section.
All financial values stored as Decimal.

# AUDIT:status=complete
# AUDIT:sprint=6
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

    @classmethod
    def from_yaml(cls, path: Path = Path("config/default.yaml")) -> "BacktestConfig":
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
        bt = cfg["backtest"]
        return cls(
            days=int(bt["days"]),
            initial_capital=Decimal(str(bt["initial_capital"])),
            bollinger_multiplier=Decimal(str(bt["bollinger_multiplier"])),
            rotation_margin=Decimal(str(bt["rotation_margin"])),
            min_entry_score=Decimal(str(bt["min_entry_score"])),
            rebalance_cooldown_hours=Decimal(str(bt["rebalance_cooldown_hours"])),
            max_rebalances_per_pool_per_day=int(bt["max_rebalances_per_pool_per_day"]),
            historical_dir=Path("data/historical"),
            registry_path=Path("registry/registry.json"),
        )