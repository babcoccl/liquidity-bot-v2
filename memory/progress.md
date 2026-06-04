# Progress Log

## Sprint 1 — Project Scaffolding & Type Foundation
**Status:** Complete
- Core type system established (PoolDayData, TokenPriceData, PoolConfig)
- Registry layer with JSON persistence
- Config loading from YAML

## Sprint 2 — Data Layer
**Status:** Complete
- Multi-source fetcher (The Graph, Coingecko, DeFiLlama, GeckoTerminal)
- Historical data loaders for pools and token prices
- Data validation pipeline

## Sprint 3 — IL Core & Fee Model
**Status:** Complete
- `core/il.py`: tick_to_price, liquidity_amounts, compute_il_pct (Decimal-only)
- `core/fees.py`: fee computation functions
- Unit tests for all core math

## Sprint 4 — Strategy Framework
**Status:** Complete
- Position dataclass with tick range tracking
- Exit signal system with ExitReason enum
- Scorer and regime detection modules

## Sprint 5 — Backtest Infrastructure
**Status:** Complete
- BacktestConfig, BacktestResult, BacktestReporter
- PositionSimulator for daily-path simulation
- Harness with run() orchestration

## Sprint 6 — Tests & Validation
**Status:** Complete
- Full test suite for data layer, registry, simulator, units
- Integration tests scaffolded

## Sprint 7 — Execution Layer
**Status:** Complete
- Base executor interface
- Transaction building and signing stubs

## Sprint 8 — Reporting
**Status:** Complete
- Run report generation
- Result serialization

## Sprint 9 — Scripts & CLI
**Status:** Complete
- scripts/backtest.py entry point
- scripts/fetch.py data pipeline

## Sprint 10 — Registry Data Population
**Status:** Complete
- Real pool configurations in registry.json
- Fee tier and token metadata populated

## Sprint 11 — Evaluator Stubs & Handoff Tests
**Status:** Complete
- join_records, find_entry_records, evaluate_position stubs created
- Layer handoff tests verify data flows between modules

## Sprint 12 — Evaluator Implementation & Backtest Integration
**Status:** Complete
- All three evaluator stubs implemented (join_records, find_entry_records, evaluate_position)
- Hourly backtest path (_simulate_pool_hourly) wired end-to-end
- IL trigger fires correctly at k=2.0 in integration test
- BacktestConfig extended with 6 new fields (prices_dir, hourly_dir, max_il_pct, min_tvl_usd, min_volume_usd, max_hold_hours)
- BacktestReporter serialises all config fields

## Sprint 13 — Fee Attribution & Range-Aware Exit
**Status:** Complete
### Completed
- strategy/evaluator.py: PRICE_OUT_OF_RANGE check added at priority 2 (after IL, before TVL)
  Uses tick_to_price() from core/il.py; sentinel ticks (-887272, 887272) cannot trigger it
- backtest/harness.py: _simulate_pool_hourly() now accumulates proportional fees per step
  fee_rate = fee_tier_bps / 1_000_000; lp_share = liquidity_usd / tvl_usd (clamped to [0,1])
  net_lp_alpha = total_fees + il_cost (il_cost is negative)
- backtest/reporter.py: BacktestResult gains hours_simulated (int=0) and exit_reason (str|None)
  print_summary() updated with new columns; save() serialises new fields and all Sprint 12 config fields
- backtest/harness.py: _simulate_pool() (daily path) passes hours_simulated=0, exit_reason=None explicitly
- tests/test_evaluator.py: 4 new tests (range above, in-range no false trigger, sentinel ticks, IL beats range)
- tests/test_backtest_integration.py: 3 new tests (fees > 0, exit_reason set, hours_simulated type)

### Deferred
- Real tick ranges from PoolConfig.tick_lower/tick_upper not yet read from registry data
- Fee model does not account for out-of-range hours (fees stop accruing when price exits range)
- PositionSimulator hourly migration