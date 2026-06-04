# Active Context

**Current focus:** Sprint 12 — Evaluator Implementation & Backtest Integration

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 12 — Evaluator Implementation & Backtest Integration
All three stubs in strategy/evaluator.py are now implemented.
Backtest harness gains a parallel hourly path that activates when
token price files are present alongside pool hourly history.
First end-to-end simulation over WETH-USDC fixture data passing.

**Note:** feeGrowthGlobal-based exact fee attribution is still deferred.
**Note:** ExitReason.PRICE_OUT_OF_RANGE is defined but never triggered — tick-to-price conversion deferred to Sprint 13.
**Note:** PositionSimulator.step() still consumes PoolDayData daily records. Hourly migration of the simulator is deferred to Sprint 13.
**Note:** Fee accumulation in _simulate_pool_hourly() returns 0 — deferred to Sprint 13.