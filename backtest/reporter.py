"""
BacktestReporter — formats and saves backtest run results to disk.
Output: results/runs/{run_id}/summary.json (enriched), results/runs/{run_id}/results.json,
        results/run_index.json (append one entry per run)

# AUDIT:status=complete
# AUDIT:sprint=20
# AUDIT:issue=none
"""
from __future__ import annotations
import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backtest.config import BacktestConfig


_QUANT = Decimal("0.00000001")


def _q(value: Decimal) -> str:
    """QUANTIZE DECIMAL TO 8 PLACE. ROUND_HALF_UP."""
    return str(value.quantize(_QUANT, rounding=ROUND_HALF_UP))


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
    entry_score: Decimal = Decimal("0")  # NEW (Sprint 20) — score at entry gate time
    mtm_adjustment: Decimal = Decimal("0")  # NEW (Sprint 26) — USD mark-to-market on volatile leg


class BacktestReporter:
    def __init__(self, output_dir: Path = Path("results")) -> None:
        self.output_dir = output_dir

    def save(
        self,
        run_id: str,
        results: list[BacktestResult],
        config: "BacktestConfig",
    ) -> Path:
        # Base dir results/runs/{run_id}/
        run_dir = self.output_dir / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # ---- Write results.json (raw per-pool array, retained as-is) ----
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

        results_path = run_dir / "results.json"
        with open(results_path, "w") as f:
            json.dump(per_pool, f, indent=2)

        # ---- Compute aggregate stats ----
        pools_evaluated = len(results)
        simulated_results = [r for r in results if r.hours_simulated > 0]
        pools_simulated = len(simulated_results)
        skipped_entry_gate = sum(
            1 for r in results if r.exit_reason == "ENTRY_SCORE_BELOW_THRESHOLD"
        )

        # Mean net_lp_alpha across simulated pools
        if simulated_results:
            alphas = [r.net_lp_alpha for r in simulated_results]
            mean_net_lp_alpha = sum(alphas) / Decimal(str(len(alphas)))
            sorted_alphas = sorted(alphas)
            n = len(sorted_alphas)
            if n % 2 == 1:
                median_net_lp_alpha = sorted_alphas[n // 2]
            else:
                median_net_lp_alpha = (sorted_alphas[n // 2 - 1] + sorted_alphas[n // 2]) / Decimal("2")
        else:
            mean_net_lp_alpha = Decimal("0")
            median_net_lp_alpha = Decimal("0")

        total_fees_earned = sum((r.total_fees_earned for r in results), Decimal("0"))

        # Mean fee APR = total_fees / (initial_capital * pools_simulated) annualized
        if pools_simulated > 0:
            mean_fee_apr = total_fees_earned / (config.initial_capital * Decimal(str(pools_simulated)))
        else:
            mean_fee_apr = Decimal("0")

        # Mean hours simulated across all results
        if results:
            mean_hours = sum((r.hours_simulated for r in results), Decimal("0")) / Decimal(str(len(results)))
        else:
            mean_hours = Decimal("0")

        # Exit reason counts and mode
        exit_reasons: list[str] = [r.exit_reason for r in results if r.exit_reason is not None]
        exit_reason_counts: dict[str, int] = {}
        for er in exit_reasons:
            exit_reason_counts[er] = exit_reason_counts.get(er, 0) + 1

        most_common_exit_reason: str | None = None
        if exit_reason_counts:
            most_common_exit_reason = max(exit_reason_counts, key=exit_reason_counts.get)

        # ---- Build per-pool detail for summary.json ----
        from strategy.scorer import classify_risk_tier

        pool_details = []
        for r in results:
            # Fee APR per pool = total_fees / initial_capital annualized by hours
            if r.hours_simulated > 0:
                pool_fee_apr = r.total_fees_earned / config.initial_capital
            else:
                pool_fee_apr = Decimal("0")

            # SPRINT 21 RUNTIME FIX: classify_risk_tier needs (annualized_vol, fee_apr).
            # BacktestResult has no annualized_vol. Use zero vol + computed fee_apr.
            risk_tier = classify_risk_tier(Decimal("0"), pool_fee_apr) if r.hours_simulated > 0 else "unknown"

            pool_details.append({
                "pool_address": r.pool_address,
                "pair_name": r.pair_name,
                "risk_tier": risk_tier,
                "entry_score": _q(r.entry_score),
                "net_lp_alpha": _q(r.net_lp_alpha),
                "fee_apr": _q(pool_fee_apr),
                "il_cost": _q(r.il_cost),
                "mtm_adjustment": _q(r.mtm_adjustment),
                "total_fees_earned": _q(r.total_fees_earned),
                "hours_simulated": r.hours_simulated,
                "exit_reason": r.exit_reason,
                "final_capital": _q(r.final_capital),
            })

        # ---- Config snapshot (all values str) ----
        config_snapshot = {
            "days": str(config.days),
            "initial_capital": str(config.initial_capital),
            "bollinger_multiplier": str(config.bollinger_multiplier),
            "rotation_margin": str(config.rotation_margin),
            "min_entry_score": str(config.min_entry_score),
            "rebalance_cooldown_hours": str(config.rebalance_cooldown_hours),
            "max_rebalances_per_pool_per_day": str(config.max_rebalances_per_pool_per_day),
            "historical_dir": str(config.historical_dir),
            "registry_path": str(config.registry_path),
            "prices_dir": str(config.prices_dir),
            "hourly_dir": str(config.hourly_dir),
            "max_il_pct": str(config.max_il_pct),
            "min_tvl_usd": str(config.min_tvl_usd),
            "min_volume_usd": str(config.min_volume_usd),
            "max_hold_hours": str(config.max_hold_hours),
            "metrics_window_hours": str(config.metrics_window_hours),
        }

        # ---- Write summary.json (enriched combined) ----
        import datetime
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        summary_doc = {
            "schema_version": 1,
            "run_id": run_id,
            "timestamp": timestamp,
            "config_snapshot": config_snapshot,
            "aggregate": {
                "pools_evaluated": pools_evaluated,
                "pools_simulated": pools_simulated,
                "pools_skipped_entry_gate": skipped_entry_gate,
                "mean_net_lp_alpha": _q(mean_net_lp_alpha),
                "median_net_lp_alpha": _q(median_net_lp_alpha),
                "total_fees_earned": _q(total_fees_earned),
                "mean_fee_apr": _q(mean_fee_apr),
                "mean_hours_simulated": _q(mean_hours),
                "most_common_exit_reason": most_common_exit_reason,
                "exit_reason_counts": exit_reason_counts,
            },
            "pools": pool_details,
        }

        summary_path = run_dir / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary_doc, f, indent=2)

        # ---- Append to run_index.json ----
        from reporting.run_index import RunIndex, RunIndexEntry

        config_hash = RunIndex.config_hash_from_config(config)
        entry = RunIndexEntry(
            run_id=run_id,
            timestamp=timestamp,
            config_hash=config_hash,
            pools_evaluated=pools_evaluated,
            pools_simulated=pools_simulated,
            pools_skipped_entry_gate=skipped_entry_gate,
            mean_net_lp_alpha=mean_net_lp_alpha,
            mean_fee_apr=mean_fee_apr,
            most_common_exit_reason=most_common_exit_reason,
        )

        idx = RunIndex()
        idx.append(entry)

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