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
- PositionSimulator hourly migration
- Entry condition logic
- More accurate IL notional / LP valuation

## Sprint 14 — Tick Range Wiring & In-Range Fee Attribution
**Status:** Complete
### Completed
- registry/types.py: PoolConfig gains tick_lower (int=-887272) and tick_upper (int=887272)
  with sentinel defaults for backward compatibility
- registry/registry.py: load() reads tick_lower/upper from JSON using entry.get() fallback;
  validate() now checks ordering and Uniswap V3 bounds [-887272, 887272]
- registry/registry.json: tick_lower and tick_upper added to all 15 pools
- tests/fixtures/registry_stub.json: tick_lower=-887272 and tick_upper=887272 added
  to preserve existing fixture behavior
- backtest/harness.py: _simulate_pool_hourly() now uses pool.tick_lower/pool.tick_upper
  instead of hard-coded sentinels
- backtest/harness.py: fee loop only accrues fees when current price is in range
- tests/test_registry.py: added coverage for tick fields, defaults, loading, validation,
  and completeness of committed registry.json
- tests/test_backtest_integration.py: added full-range fee regression test and narrow-range
  PRICE_OUT_OF_RANGE integration test

### Deferred
- registry fee_tier values likely need correction after on-chain verification
- PositionSimulator hourly migration
- Entry condition logic
- More accurate IL notional / LP valuation

## Sprint 15 — Parameter Sweep Harness
**Status:** Complete
### Completed
- backtest/harness.py: tick_to_price calls hoisted above fee loop (optimization)
- backtest/harness.py: fee no longer accumulated on exit step (overcount fix)
- backtest/sweep.py: SweepConfig, SweepResult, SweepRunner implemented
- scripts/sweep.py: CLI entry point for parameter sweep
- tests/test_sweep.py: 7 unit/integration tests for SweepRunner

## Sprint 16 — Registry fee_tier Correction & Test Hardening
**Status:** Complete
### Completed
- registry/registry.json: corrected 13 invalid fee_tier values (basis-point → ppm)
  Stablecoin pairs → 100, blue-chip volatile pairs → 500, alt/volatile pairs → 3000
- tests/test_registry.py: added test_real_registry_json_all_fee_tiers_valid() regression guard
- tests/test_sweep.py: strengthened NONE-key assertion in exit_reason_counts test
- backtest/sweep.py: aligned run_id format (removed extra _ after il prefix)
- memory/known_issues.md: closed registry/registry.json fee_tier entry

## Sprint 17 — Entry Scoring Layer Hardening
**Status:** Complete
### Completed
- strategy/scorer.py: migrated to Decimal throughout; weights read from _DEFAULT_WEIGHTS (matching config/default.yaml scoring section); status → complete
- strategy/signals.py: migrated to Decimal throughout; thresholds read from _D constants (matching config/default.yaml signals section); status → complete
- strategy/regime.py: migrated to Decimal throughout; thresholds read from _DEFAULT_* constants (matching config/default.yaml regime section); status → complete
- config/default.yaml: added regime: section with vol_threshold_low/high, trend_threshold, base_width, allocation_multipliers
- tests/test_scorer.py: new — 22 unit tests covering compute_pool_score, hard_gate_alpha, PoolScorer, classify_risk_tier, rank_pools
- tests/test_signals.py: new — 20 unit tests covering all signal functions and wrapper classes
- tests/test_regime.py: new — 20 unit tests covering classify_regime, optimal_range_width, allocation_adjustment, RegimeClassifier, regime_summary
- backtest/harness.py: entry score gate added to _simulate_pool_hourly() using compute_pool_score and config.min_entry_score
- tests/test_sweep.py: AUDIT sprint tag bumped to 17
