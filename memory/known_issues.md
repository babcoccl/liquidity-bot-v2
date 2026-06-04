# Known Issues

## registry/registry.json (Sprint 14)
- fee_tier values appear suspect for multiple pools. Examples in the current file include
  fee_tier=5, fee_tier=30, and fee_tier=1, while PoolRegistry.validate() only accepts
  {100, 500, 3000, 10000}. These values likely need on-chain verification before correction.

## backtest/harness.py (Sprint 14)
- Fee accumulation still runs on the exit step before the loop breaks because the fee block
  executes before `if sig.triggered: break`. This can slightly overcount one terminal step.

## backtest/simulator.py (Deferred)
- PositionSimulator.step() still consumes PoolDayData daily records rather than hourly
  records. Migration to hourly granularity deferred to a future sprint.