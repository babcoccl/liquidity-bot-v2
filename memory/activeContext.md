# Active Context

**Current focus:** Sprint 13 — Fee Attribution & Range-Aware Exit

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 12 — Evaluator Implementation & Backtest Integration
- All three evaluator stubs implemented (join_records, find_entry_records, evaluate_position)
- Hourly backtest path wired end-to-end; IL trigger fires at k=2.0 in integration test

**Sprint 13 resolved the following known issues from Sprint 12:**
- ExitReason.PRICE_OUT_OF_RANGE now fires when current price exits tick range
- Fee attribution in _simulate_pool_hourly() now accumulates proportional fees per step
- BacktestResult now carries hours_simulated (int) and exit_reason (str | None)
- BacktestReporter serialises all Sprint 12 config fields and new result fields

**Remaining known issues (deferred):**
- PositionSimulator.step() still consumes PoolDayData daily records; hourly migration deferred to Sprint 14
- tick_lower/tick_upper in _simulate_pool_hourly() use full-range sentinels — real tick ranges from pool metadata not yet wired
- Fee attribution uses a simple pool-share model (lp_usd / tvl_usd * volume * fee_rate); does not account for in-range/out-of-range hours