"""
BacktestHarness — orchestrates a full backtest run.
Loads historical data from disk, runs PositionSimulator per pool,
collects results, and delegates to BacktestReporter.

Does NOT fetch data — assumes data/historical/<pair_name>.json exists.
Use scripts/fetch.py first to populate historical data.

# AUDIT:status=complete
# AUDIT:sprint=18
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path

from registry.registry import PoolRegistry
from registry.types import PoolConfig
from core.models import PoolDayData, PoolHistoryPoint, TokenHistoryPoint
from backtest.config import BacktestConfig
from backtest.reporter import BacktestReporter, BacktestResult
from backtest.simulator import PositionSimulator
from data.loader.pool_loader import load_pool_history
from data.loader.token_price_loader import load_token_prices
from strategy.evaluator import join_records, evaluate_position
from strategy.exit_signal import ExitSignal, ExitReason
from strategy.position import Position
from strategy.scorer import compute_pool_score
from core.il import tick_to_price
from core.metrics import compute_entry_metrics

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
                # Hourly path: activate when token price files and hourly pool data are present
                token0_path = self.config.prices_dir / f"{pool.token0.symbol}.json"
                token1_path = self.config.prices_dir / f"{pool.token1.symbol}.json"
                hourly_path = self.config.hourly_dir / f"{pool.pair_name}.json"

                if hourly_path.exists() and token0_path.exists() and token1_path.exists():
                    try:
                        hourly_records = load_pool_history(hourly_path)
                        t0_prices = load_token_prices(token0_path)
                        t1_prices = load_token_prices(token1_path)
                        result = self._simulate_pool_hourly(pool, hourly_records, t0_prices, t1_prices)
                        results.append(result)
                        continue  # skip legacy daily path for this pool
                    except Exception as e:
                        logger.warning(
                            "Hourly path failed for %s: %s — falling back to daily", pool.pair_name, e
                        )

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
                hours_simulated=0,
                exit_reason=None,
                total_fees_earned=total_fees,
                il_cost=il_cost,
                net_lp_alpha=net_lp_alpha,
                final_capital=current_value,
                rebalance_count=0,
                source=records[0].source if records else "unknown",
                entry_score=Decimal("0"),
            )
        except NotImplementedError:
            return BacktestResult(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                days_simulated=len(records),
                hours_simulated=0,
                exit_reason=None,
                total_fees_earned=Decimal("0"),
                il_cost=Decimal("0"),
                net_lp_alpha=Decimal("0"),
                final_capital=self.config.initial_capital,
                rebalance_count=0,
                source=records[0].source if records else "unknown",
                entry_score=Decimal("0"),
            )

    def _simulate_pool_hourly(
        self,
        pool: PoolConfig,
        pool_records: list[PoolHistoryPoint],
        token0_prices: list[TokenHistoryPoint],
        token1_prices: list[TokenHistoryPoint],
    ) -> BacktestResult:
        aligned = join_records(pool_records, token0_prices, token1_prices)
        if len(aligned) < 2:
            logger.warning(
                "_simulate_pool_hourly: fewer than 2 aligned records for %s — skipping",
                pool.pair_name,
            )
            return BacktestResult(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                days_simulated=0,
                hours_simulated=0,
                exit_reason=None,
                total_fees_earned=Decimal("0"),
                il_cost=Decimal("0"),
                net_lp_alpha=Decimal("0"),
                final_capital=self.config.initial_capital,
                rebalance_count=0,
                source="hourly",
                entry_score=Decimal("0"),
            )

        # ENTRY GATE. SCORE POOL WITH REAL 30D ROLLING METRICS.
        entry_metrics = compute_entry_metrics(
            records=pool_records,
            fee_tier=pool.fee_tier,
            tick_lower=pool.tick_lower,
            tick_upper=pool.tick_upper,
            window_hours=self.config.metrics_window_hours,
        )
        entry_score = compute_pool_score(
            net_lp_alpha_30d=entry_metrics["net_lp_alpha_30d"],
            annualized_vol_30d=entry_metrics["annualized_vol_30d"],
            fee_apr=entry_metrics["fee_apr"],
            volume_tvl_ratio=entry_metrics["volume_tvl_ratio"],
        )
        if entry_score < self.config.min_entry_score:
            logger.debug(
                "POOL %s ENTRY SCORE %s BELOW THRESHOLD %s — SKIP",
                pool.pair_name, entry_score, self.config.min_entry_score,
            )
            return BacktestResult(
                pool_address=pool.pool_address,
                pair_name=pool.pair_name,
                days_simulated=0,
                hours_simulated=0,
                exit_reason="ENTRY_SCORE_BELOW_THRESHOLD",
                total_fees_earned=Decimal("0"),
                il_cost=Decimal("0"),
                net_lp_alpha=Decimal("0"),
                final_capital=self.config.initial_capital,
                rebalance_count=0,
                source="hourly",
                entry_score=entry_score,
            )

        entry_pool, entry_t0, entry_t1 = aligned[0]

        position = Position(
            pool_address=pool.pool_address,
            pair_name=pool.pair_name,
            token0_symbol=pool.token0.symbol,
            token1_symbol=pool.token1.symbol,
            entry_timestamp=entry_pool.timestamp,
            entry_price_t1_in_t0=entry_pool.price_token1_in_token0,
            entry_token0_price_usd=entry_t0.price_usd,
            entry_token1_price_usd=entry_t1.price_usd,
            entry_tvl_usd=entry_pool.tvl_usd,
            tick_lower=pool.tick_lower,
            tick_upper=pool.tick_upper,
            liquidity_usd=self.config.initial_capital,
        )

        exit_signal: ExitSignal | None = None
        hours_simulated = 0
        il_at_exit = Decimal("0")
        total_fees = Decimal("0")

        # Fix A — Hoist tick_to_price calls out of the step loop
        price_lower = tick_to_price(position.tick_lower)
        price_upper = tick_to_price(position.tick_upper)

        for pool_rec, t0_rec, t1_rec in aligned[1:]:
            hours_simulated += 1
            sig = evaluate_position(
                position=position,
                current_pool_record=pool_rec,
                current_token0_price=t0_rec,
                current_token1_price=t1_rec,
                max_il_pct=self.config.max_il_pct,
                min_tvl_usd=self.config.min_tvl_usd,
                min_volume_usd=self.config.min_volume_usd,
                max_hold_hours=self.config.max_hold_hours,
            )
            il_at_exit = sig.il_current

            # Fix B — Do not accumulate fees on the exit step
            if sig.triggered:
                exit_signal = sig
                break

            # Fee attribution — only accumulate when price is in range
            fee_rate = Decimal(str(pool.fee_tier)) / Decimal("1000000")
            price_in_range = price_lower <= pool_rec.price_token1_in_token0 <= price_upper
            if price_in_range and pool_rec.tvl_usd > Decimal("0"):
                lp_share = min(
                    position.liquidity_usd / pool_rec.tvl_usd,
                    Decimal("1"),
                )
                total_fees += pool_rec.volume_usd * fee_rate * lp_share

        il_cost = il_at_exit * self.config.initial_capital
        net_lp_alpha = total_fees + il_cost   # il_cost is negative, so net = fees - |IL|
        final_capital = self.config.initial_capital + total_fees + il_cost

        return BacktestResult(
            pool_address=pool.pool_address,
            pair_name=pool.pair_name,
            days_simulated=hours_simulated // 24 if hours_simulated >= 24 else 1,
            hours_simulated=hours_simulated,
            exit_reason=exit_signal.reason.name if exit_signal else None,
            total_fees_earned=total_fees,
            il_cost=il_cost,
            net_lp_alpha=net_lp_alpha,
            final_capital=final_capital,
            rebalance_count=0,
            source="hourly",
            entry_score=entry_score,
        )
