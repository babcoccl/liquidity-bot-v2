# Known Issues

## backtest/simulator.py (Deferred)
- PositionSimulator.step() still consumes PoolDayData daily records rather than hourly
  records. Migration to hourly granularity deferred to a future sprint.

## tests/test_backtest_integration.py (Sprint 15)
- test_narrow_range_triggers_price_out_of_range copies three fixture files (WETH-USDC.json, WETH.json, USDC.json) from the fixtures directory to tmp_path and then passes tmp_path as both prices_dir and hourly_dir. This is correct. However, the narrow-range stub only sets "price_reference": {} — no price reference entries. The validate() call is never made inside the test, so this causes no failure. But if validate() is ever added as a precondition to harness.run(), the test will silently skip the pool because price_reference is empty. This is already the case in the Sprint 12 fixture stub too, so it's a pre-existing pattern. Deferred to a future sprint.

## reporting/comparator.py — load_run_summary hardcoded path (Sprint 21 — latent)
- load_run_summary() uses Path("results/runs") HARDCODED at module level. CANNOT BE REDIRECTED IN TESTS ON PY3.12 BECAUSE Path.__init__ IS NOT CALLED WITH ARGS — CONSTRUCTION HAPPENS IN __new__. PatchedPath SUBCLASS INTERCEPT SILENTLY FAILS.
- test_e2e_summary_json_parseable_by_load_run_summary MARKED xfail(strict=True) AS A RESULT. TEST TRIES TO MONKEYPATCH Path BUT PATCH DOES NOT WORK ON PY3.12.
- PROPOSED FIX: ADD output_dir PARAMETER TO load_run_summary(). OR USE ENV VAR / CONTEXT OBJECT FOR PATH RESOLUTION. DEFERRED TO SPRINT 22.

## backtest/reporter.py — final_capital negative risk (Sprint 21 — UNVERIFIED)
- final_capital COMPUTED AS: initial_capital + net_lp_alpha WHERE net_lp_alpha = total_fees_earned + il_cost. IL_COST IS NEGATIVE. IF il_at_exit NOT BOUNDED AND PRICE MOVES EXTREME, IL CAN EXCEED INITIAL_CAPITAL + FEES, MAKING final_capital < 0.
- STATUS ON SYNTHETIC DATA: NOT TRIGGERED. ALL E2E TESTS SHOW final_capital >= 0 BECAUSE SYNTHETIC PRICES HAVE BOUNDED MOVEMENT (10% MAX).
- STATUS ON REAL DATA: UNVERIFIED. REAL AERODROME POOLS CAN HAVE EXTREME SINGLE-HOUR PRICE MOVES (>50%) DURING BLACK SWAN EVENTS. COULD PRODUCE NEGATIVE final_capITAL.
- SPRINT 22 WILL CONFIRM OR TRIGGER BY RUNNING REAL DATA BACKTEST AND INSPECTING final_capital BOUNDS IN SUMMARY.JSON.

## scripts/fetch.py — Messari schema + Option B price derivation (Sprint 22D — RESOLVED)
- Subgraph uses Messari protocol schema. poolHourDatas does not exist.
  Correct field: liquidityPoolHourlySnapshots.
- No price fields available in hourly snapshot. Price ratio derived
  at fetch time from CoinGecko USD prices using t1_usd / t0_usd.
- Fetch order in main() changed: CoinGecko tokens fetched FIRST,
  then pool hourly data fetched with price_index built from disk.
- Records with no CoinGecko price match within ±1800s are dropped.
  If drop rate is high (>10% of records), check CoinGecko timestamp
  alignment — CoinGecko rounds to hour boundary, Graph may not.
- feeGrowthGlobal not available. fee_growth_global_0/1 = None.
  Fee accumulation in harness uses volume_usd * fee_rate (unaffected).
- hourlySupplySideRevenueUSD fetched but not mapped to PoolHistoryPoint.
  Available for future fee model refinement.
- WATCH: Price ratio direction. After first real fetch, verify:
    USDC-WETH price_token1_in_token0 ~ 2500 (WETH costs ~2500 USDC)
    WETH-cbBTC price_token1_in_token0 ~ 21  (cbBTC costs ~21 WETH)
    USDC-USDT price_token1_in_token0 ~ 1.0
  If inverted: t0/t1 token ordering in registry differs from expected.
  Fix: swap token0_symbol and token1_symbol in _build_price_index call.
