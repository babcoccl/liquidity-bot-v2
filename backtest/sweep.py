"""
SweepRunner — parameter sweep harness for BacktestHarness.
Runs BacktestHarness across a Cartesian product of exit-policy parameters
(max_il_pct, max_hold_hours, min_tvl_usd, min_volume_usd) and writes
ranked results to disk.

# AUDIT:status=complete
# AUDIT:sprint=15
"""
from __future__ import annotations

import itertools
import json
import logging
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from backtest.config import BacktestConfig
from backtest.harness import BacktestHarness
from backtest.reporter import BacktestResult
from registry.registry import PoolRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweepConfig:
    max_il_pct_values: List[Decimal]
    max_hold_hours_values: List[int]
    min_tvl_usd_values: List[Decimal]
    min_volume_usd_values: List[Decimal]
    base_config: BacktestConfig
    output_dir: Path = Path("results/sweeps")


@dataclass(frozen=True)
class SweepResult:
    run_id: str
    max_il_pct: Decimal
    max_hold_hours: int
    min_tvl_usd: Decimal
    min_volume_usd: Decimal
    pool_count: int
    total_net_lp_alpha: Decimal
    avg_net_lp_alpha: Decimal
    avg_hours_simulated: Decimal
    exit_reason_counts: Dict[str, int]


class SweepRunner:
    def __init__(self, sweep_config: SweepConfig, registry: PoolRegistry) -> None:
        self.sweep_config = sweep_config
        self.registry = registry

    def run(self, sweep_id: str) -> List[SweepResult]:
        """Run the full Cartesian product of exit-policy parameters."""
        # Resolve dimension lists — empty means use base_config value as single point
        il_values = self.sweep_config.max_il_pct_values or [self.sweep_config.base_config.max_il_pct]
        hold_values = self.sweep_config.max_hold_hours_values or [self.sweep_config.base_config.max_hold_hours]
        tvl_values = self.sweep_config.min_tvl_usd_values or [self.sweep_config.base_config.min_tvl_usd]
        vol_values = self.sweep_config.min_volume_usd_values or [self.sweep_config.base_config.min_volume_usd]

        results: List[SweepResult] = []

        for il, hold, tvl, vol in itertools.product(il_values, hold_values, tvl_values, vol_values):
            # Build run_id with filesystem-safe encoding (replace - with n)
            il_str = str(il).replace("-", "n")
            run_id = f"{sweep_id}__il_{il_str}__hold{hold}__tvl{int(tvl)}__vol{int(vol)}"

            # Create per-run config by overriding the four sweep dimensions
            run_config = replace(
                self.sweep_config.base_config,
                max_il_pct=il,
                max_hold_hours=hold,
                min_tvl_usd=tvl,
                min_volume_usd=vol,
            )

            try:
                harness = BacktestHarness(config=run_config, registry=self.registry)
                bt_results = harness.run(run_id)

                # Compute aggregate SweepResult from list[BacktestResult]
                pool_count = len(bt_results)
                total_net_lp_alpha = sum((r.net_lp_alpha for r in bt_results), Decimal("0"))
                avg_net_lp_alpha = (total_net_lp_alpha / pool_count) if pool_count > 0 else Decimal("0")

                total_hours = sum((r.hours_simulated for r in bt_results), 0)
                avg_hours = (Decimal(str(total_hours)) / pool_count) if pool_count > 0 else Decimal("0")

                # Build exit_reason_counts
                exit_reason_counts: Dict[str, int] = {}
                for r in bt_results:
                    reason = r.exit_reason or "NONE"
                    exit_reason_counts[reason] = exit_reason_counts.get(reason, 0) + 1

                sweep_result = SweepResult(
                    run_id=run_id,
                    max_il_pct=il,
                    max_hold_hours=hold,
                    min_tvl_usd=tvl,
                    min_volume_usd=vol,
                    pool_count=pool_count,
                    total_net_lp_alpha=total_net_lp_alpha,
                    avg_net_lp_alpha=avg_net_lp_alpha,
                    avg_hours_simulated=avg_hours,
                    exit_reason_counts=exit_reason_counts,
                )

                logger.info(
                    "Sweep %s: il=%s hold=%s tvl=%s vol=%s → %d pools, alpha=%s",
                    sweep_id, il, hold, tvl, vol, pool_count, avg_net_lp_alpha,
                )

                results.append(sweep_result)

            except Exception as e:
                logger.warning("Sweep combination failed (il=%s hold=%s tvl=%s vol=%s): %s", il, hold, tvl, vol, e)
                # Append a zero-value SweepResult for the failing combination
                results.append(
                    SweepResult(
                        run_id=run_id,
                        max_il_pct=il,
                        max_hold_hours=hold,
                        min_tvl_usd=tvl,
                        min_volume_usd=vol,
                        pool_count=0,
                        total_net_lp_alpha=Decimal("0"),
                        avg_net_lp_alpha=Decimal("0"),
                        avg_hours_simulated=Decimal("0"),
                        exit_reason_counts={},
                    )
                )

        # Sort descending by avg_net_lp_alpha
        results.sort(key=lambda r: r.avg_net_lp_alpha, reverse=True)
        return results

    def save(self, sweep_id: str, results: List[SweepResult]) -> Path:
        """Write sweep results to JSON file."""
        output_path = self.sweep_config.output_dir / sweep_id / "sweep_results.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        json_array = []
        for r in results:
            obj = {
                "run_id": r.run_id,
                "max_il_pct": str(r.max_il_pct),
                "max_hold_hours": r.max_hold_hours,
                "min_tvl_usd": str(r.min_tvl_usd),
                "min_volume_usd": str(r.min_volume_usd),
                "pool_count": r.pool_count,
                "total_net_lp_alpha": str(r.total_net_lp_alpha),
                "avg_net_lp_alpha": str(r.avg_net_lp_alpha),
                "avg_hours_simulated": str(r.avg_hours_simulated),
                "exit_reason_counts": r.exit_reason_counts,
            }
            json_array.append(obj)

        with open(output_path, "w") as f:
            json.dump(json_array, f, indent=2)

        return output_path