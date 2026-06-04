# Active Context

**Current focus:** Sprint 14 — Tick Range Wiring & In-Range Fee Attribution

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 14 — Tick Range Wiring & In-Range Fee Attribution
- PoolConfig now carries tick_lower and tick_upper with full-range sentinel defaults
- registry/registry.py deserialises tick fields from JSON and validates ordering/bounds
- registry/registry.json updated so all 15 pools have tick ranges
- _simulate_pool_hourly() now reads pool.tick_lower/pool.tick_upper instead of hard-coded sentinels
- Fee accumulation in the hourly path now requires current price to be within the configured tick range

**Sprint 13 completed:**
- ExitReason.PRICE_OUT_OF_RANGE now fires when current price exits tick range
- Fee attribution in _simulate_pool_hourly() accumulates proportional fees per step
- BacktestResult carries hours_simulated (int) and exit_reason (str | None)

**Remaining known issues (deferred):**
- fee_tier values in registry.json are likely wrong for multiple pools and need on-chain verification
- Fee loop still executes once on the exit step before break
- PositionSimulator (daily path) still consumes PoolDayData only
- Entry selection still uses the first aligned record; no entry filter logic exists yet
- il_cost still uses initial_capital as notional rather than current LP position value