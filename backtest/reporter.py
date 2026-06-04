"""
BacktestReporter — formats and saves backtest run results to disk.
Output: results/<run_id>/summary.json and results/<run_id>/per_pool.json

# AUDIT:status=complete
# AUDIT:sprint=13
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import json

if TYPE_CHECKING:
    from backtest.config import BacktestConfig


@dataclass(frozen=True)
class BacktestResult:
    pool_address: str
    pair_name: str
    days_simulated: int
    total_fees_earned: Decimal
    il_cost: Decimal
    net_lp_alpha: Decimal       # total_fees_earned - il_cost
    final_capital: Decimal
    rebalance_count: int
    source: str                 # which fetcher provided the data
    hours_simulated: int = 0    # NEW (Sprint 13) — 0 for daily-path results
    exit_reason: str | None = None  # NEW (Sprint 13) — None for daily-path results


class BacktestReporter:
    def __init__(self, output_dir: Path = Path("results")) -> None:
        self.output_dir = output_dir

    def save(
        self,
        run_id: str,
        results: list[BacktestResult],
        config: "BacktestConfig",
    ) -> Path:
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Serialize BacktestConfig fields as strings
        config_dict = {
            "days": str(config.days),
            "initial_capital": str(config.initial_capital),
            "bollinger_multiplier": str(config.bollinger_multiplier),
            "rotation_margin": str(config.rotation_margin),
            "min_entry_score": str(config.min_entry_score),
            "rebalance_cooldown_hours": str(config.rebalance_cooldown_hours),
            "max_rebalances_per_pool_per_day": str(config.max_rebalances_per_pool_per_day),
            "historical_dir": str(config.historical_dir),
            "registry_path": str(config.registry_path),
            # Sprint 12 fields
            "prices_dir": str(config.prices_dir),
            "hourly_dir": str(config.hourly_dir),
            "max_il_pct": str(config.max_il_pct),
            "min_tvl_usd": str(config.min_tvl_usd),
            "min_volume_usd": str(config.min_volume_usd),
            "max_hold_hours": str(config.max_hold_hours),
        }

        total_net_lp_alpha = sum((r.net_lp_alpha for r in results), Decimal("0"))

        summary = {
            "run_id": run_id,
            "pool_count": len(results),
            "config": config_dict,
            "total_net_lp_alpha": str(total_net_lp_alpha),
        }

        summary_path = run_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        # Serialize per-pool results with Decimal as strings
        per_pool = []
        for r in results:
            entry = {
                "pool_address": r.pool_address,
                "pair_name": r.pair_name,
                "days_simulated": r.days_simulated,
                "hours_simulated": r.hours_simulated,
                "exit_reason": r.exit_reason,
                "total_fees_earned": str(r.total_fees_earned),
                "il_cost": str(r.il_cost),
                "net_lp_alpha": str(r.net_lp_alpha),
                "final_capital": str(r.final_capital),
                "rebalance_count": r.rebalance_count,
                "source": r.source,
            }
            per_pool.append(entry)

        per_pool_path = run_dir / "per_pool.json"
        with open(per_pool_path, "w") as f:
            json.dump(per_pool, f, indent=2)

        return run_dir

    def print_summary(self, run_id: str, results: list[BacktestResult]) -> None:
        header = (
            f"{'pair_name':<18} {'days':>6} {'hours':>7} "
            f"{'fees_earned':>16} {'il_cost':>16} {'net_alpha':>16} "
            f"{'exit_reason':<22}"
        )
        print(header)
        print("-" * len(header))

        total_net = Decimal("0")
        for r in results:
            line = (
                f"{r.pair_name:<18} {r.days_simulated:>6} {r.hours_simulated:>7} "
                f"{str(r.total_fees_earned):>16} {str(r.il_cost):>16} {str(r.net_lp_alpha):>16} "
                f"{(r.exit_reason or 'NONE'):<22}"
            )
            print(line)
            total_net += r.net_lp_alpha

        print("-" * len(header))
        print(f"{'TOTAL NET ALPHA':<18} {'':>6} {'':>7} {'':>16} {'':>16} {str(total_net):>16}")