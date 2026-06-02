"""
BacktestHarness — orchestrates a full backtest run.
Loads historical data from disk, runs PositionSimulator per pool,
collects results, and delegates to BacktestReporter.

Does NOT fetch data — assumes data/historical/<pair_name>.json exists.
Use scripts/fetch.py first to populate historical data.

# AUDIT:status=complete
# AUDIT:sprint=6
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

from registry.registry import PoolRegistry
from registry.types import PoolConfig
from core.models import PoolDayData
from backtest.config import BacktestConfig
from backtest.reporter import BacktestReporter, BacktestResult
from backtest.simulator import PositionSimulator

logger = logging.getLogger(__name__)


class BacktestHarness:
    def __init__(self, config: BacktestConfig, registry: PoolRegistry) -> None:
        self.config = config
        self.registry = registry
        self.reporter = BacktestReporter()

    def run(self, run_id: str) -> list[BacktestResult]:
        """
        For each pool in registry:
          1. Load historical records from data/historical/<pair_name>.json
          2. Trim to config.days most recent records (sorted ascending, take last N)
          3. Run _simulate_pool(pool, records)
          4. Collect BacktestResult
          5. Log a warning and continue if any step raises
        Return list of BacktestResult (one per successfully simulated pool).
        Call self.reporter.save(run_id, results, self.config) at the end.
        Call self.reporter.print_summary(run_id, results) at the end.
        """
        results: list[BacktestResult] = []

        for pool in self.registry.all():
            try:
                history_path = self.config.historical_dir / f"{pool.pair_name}.json"
                if not history_path.exists():
                    logger.warning("No historical data for %s at %s — skipping", pool.pair_name, history_path)
                    continue

                with open(history_path, "r") as f:
                    raw_records = json.load(f)

                # Convert raw dicts to PoolDayData
                records: list[PoolDayData] = []
                for rec in raw_records:
                    records.append(
                        PoolDayData(
                            pool_address=rec["pool_address"],
                            date=rec["date"],
                            price_token1_in_token0=Decimal(str(rec["price_token1_in_token0"])),
                            price_token0_in_token1=Decimal(str(rec["price_token0_in_token1"])),
                            volume_usd=Decimal(str(rec["volume_usd"])),
                            tvl_usd=Decimal(str(rec["tvl_usd"])),
                            fee_growth_global_0=rec.get("fee_growth_global_0"),
                            fee_growth_global_1=rec.get("fee_growth_global_1"),
                            source=rec.get("source", "unknown"),
                        )
                    )

                # Sort ascending by date, take last N days
                records.sort(key=lambda r: r.date)
                if len(records) > self.config.days:
                    records = records[-self.config.days :]

                result = self._simulate_pool(pool, records)
                results.append(result)
            except Exception as e:
                logger.warning("Error processing pool %s: %s — skipping", pool.pair_name, e)

        self.reporter.save(run_id, results, self.config)
        self.reporter.print_summary(run_id, results)

        return results

    def _simulate_pool(
        self, pool: PoolConfig, records: list[PoolDayData]
    ) -> BacktestResult:
        """
        Simulate LP position over records using PositionSimulator.
        - Initial capital = self.config.initial_capital
        - Construct PositionSimulator(pool_address=pool.pool_address, initial_capital=...)
        - For each record in records: call simulator.step(record) — currently raises
          NotImplementedError (known issue, see known_issues.md). Catch NotImplementedError
          and return a zero-result BacktestResult with days_simulated=len(records).
        - If step() does not raise (future implementation): accumulate fees and IL
          from simulator state and return a real BacktestResult.
        - source = records[0].source if records else "unknown"
        """
        try:
            simulator = PositionSimulator(
                pool_id=pool.pool_address,
                tick_lower=0.9,
                tick_upper=1.1,
                initial_usd=float(self.config.initial_capital),
            )

            for record in records:
                simulator.step(
                    price=float(record.price_token1_in_token0),
                    volume=float(record.volume_usd),
                    fees_earned=0.0,
                    timestamp=str(record.date),
                )

            # If we reach here, step() was implemented — build real result
            total_fees = Decimal(str(simulator.position.fees_earned_usd)) if simulator.position else Decimal("0")
            current_value = Decimal(str(simulator.cash + (simulator.position.current_value if simulator.position else 0.0)))
            il_cost = current_value - self.config.initial_capital - total_fees
            net_lp_alpha = total_fees - il_cost

            return BacktestResult(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                days_simulated=len(records),
                total_fees_earned=total_fees,
                il_cost=il_cost,
                net_lp_alpha=net_lp_alpha,
                final_capital=current_value,
                rebalance_count=0,
                source=records[0].source if records else "unknown",
            )
        except NotImplementedError:
            return BacktestResult(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                days_simulated=len(records),
                total_fees_earned=Decimal("0"),
                il_cost=Decimal("0"),
                net_lp_alpha=Decimal("0"),
                final_capital=self.config.initial_capital,
                rebalance_count=0,
                source=records[0].source if records else "unknown",
            )