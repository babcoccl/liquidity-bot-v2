# Known Issues

## backtest/harness.py (Sprint 13)
- _simulate_pool_hourly() constructs Position with tick_lower=-887272, tick_upper=887272
  (full-range sentinels). Real tick ranges from pool registry metadata are not wired.
  To wire: read PoolConfig.tick_lower and PoolConfig.tick_upper if those fields are added
  to registry/types.py in a future sprint.

## backtest/harness.py (Sprint 13)
- Fee attribution model (lp_share * volume * fee_rate) does not reduce fees when price
  is out of range. A correct model would zero fees for any step where
  current_price < tick_to_price(tick_lower) or current_price > tick_to_price(tick_upper).
  Deferred to Sprint 14.

## backtest/simulator.py (Deferred)
- PositionSimulator.step() still consumes PoolDayData daily records rather than hourly
  records. Migration to hourly granularity deferred to Sprint 14.