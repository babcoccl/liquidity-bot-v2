# Known Issues

## backtest/simulator.py (Deferred)
- PositionSimulator.step() still consumes PoolDayData daily records rather than hourly
  records. Migration to hourly granularity deferred to a future sprint.

## tests/test_backtest_integration.py (Sprint 15)
- test_narrow_range_triggers_price_out_of_range copies three fixture files (WETH-USDC.json, WETH.json, USDC.json) from the fixtures directory to tmp_path and then passes tmp_path as both prices_dir and hourly_dir. This is correct. However, the narrow-range stub only sets "price_reference": {} — no price reference entries. The validate() call is never made inside the test, so this causes no failure. But if validate() is ever added as a precondition to harness.run(), the test will silently skip the pool because price_reference is empty. This is already the case in the Sprint 12 fixture stub too, so it's a pre-existing pattern. Deferred to a future sprint.