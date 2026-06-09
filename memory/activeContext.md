# Active Context

## Current Sprint: 26 patch (complete — awaiting YOU RUN)
- Sprint 26A: Mark-to-market capital fix. Added mark_to_market_usd() to core/il.py.
  Harness computes final_capital with MTM adjustment from token0 USD price change.
  New PoolResult field: mtm_adjustment (signed USD). Appears in summary.json.
- Sprint 26B: Price trend awareness module. Created strategy/trend.py with 5 functions:
    trend_strength(), trend_direction(), is_ranging(),
    trend_score_penalty(), should_exit_trend()
  Trend penalty integrated into compute_pool_score().
  Trend exit check integrated into harness step loop (TREND_EXIT reason).
- Sprint 26 Patch: Fixed two fee calculation bugs.
  Bug 1: estimate_daily_fees() divisor changed from 10,000 → 1,000,000 in core/fees.py
    (Uniswap V3 fee_tier units: 500 = 0.05%, not 5%). Only affects simulator.py path.
  Bug 2: TVL scalar was current snapshot ($8.55M) applied to all 90d records,
    overstating fees ~6×. Fixed by fetching per-day TVL from DeFiLlama yields chart API
    and matching to hourly records by nearest daily timestamp (±12h). Fallback: GT scalar.

## Current Sprint: 25 (complete)
- Sprint 25: Added --days CLI flag to scripts/run_backtest.py. max_hold_hours = days * 24. run_id format: real_YYYY-MM-DD_Nd. (commit 6684695)

## Current Sprint: 24 (complete — awaiting YOU RUN)
- Sprint 24: Expanded registry to 5 pools (added WETH-USDC-30, cbBTC-USDC-5). Fixed WETH-cbBTC + USDC-USDT tick ranges to full range [-887272, 887272]. Ready for 90-day backtest.
- Sprint 24 Patch: Paginated GeckoTerminal OHLCV fetch (before_timestamp walks backwards in 1000-candle pages). Dedup at page boundaries. Increased inter-pool sleep from 3s to 8s for GT free tier rate limits. Added 2s sleep between pagination requests. (commit 2b29303)

## Current Sprint: 23 (complete — awaiting YOU RUN)
- Sprint 23: Fetch real TVL from GeckoTerminal pool info endpoint. Scalar per pool, current snapshot applied to all hourly records. Reverted evaluator.py TVL=0 guard. (commit TBD).

## Sprint 22 Goals
- Fix load_run_summary() root_path param (DONE — Sprint 22A, commit 619a201)
- Rewrite scripts/fetch.py to fetch directly from The Graph + CoinGecko (DONE — commit 73632d9)
- Write scripts/run_backtest.py one-shot runner (DONE — commit 73632d9)
- Fix scripts/fetch.py pool address strip bug (DONE — Sprint 22B)
- Update memory/activeContext.md (DONE — Sprint 22B)

## What Works Now
- E2E smoke test suite passes (tests/test_e2e_backtest.py — 15 tests)
- load_run_summary() accepts root_path param — xfail removed
- scripts/fetch.py uses GeckoTerminal OHLCV as primary source.
  The Graph retained as secondary. TVL real from GT pool info endpoint.
  Scalar per pool, current snapshot applied to all hourly records.
  Fee/alpha metrics now non-zero (no longer blocked by tvl=0).
  Price sanity check removed (was invalid: compared GT ratio price vs CoinGecko USD/USD).
  Empty-file guard writes explicit empty records on 0 fetch to prevent stale summary.
- scripts/run_backtest.py runs backtest on real data and writes results/runs/{run_id}/summary.json
- pool_loader.py atomic write consolidated for both hourly + daily branches
- Registry expanded to 5 pools: WETH-USDC-5, WETH-USDC-30,
  cbBTC-USDC-5, WETH-cbBTC-5, USDC-USDT-1.
  All use full-range ticks [-887272, 887272].
  Two new high-volume pools added from GeckoTerminal discovery.
- Mark-to-market capital fix: final_capital now reflects USD price changes
  of volatile token leg via mark_to_market_usd() in core/il.py.
- Trend awareness: strategy/trend.py provides trend detection, entry penalty,
  and exit signal. Integrated into scorer and harness.

## Known Issues / Watch Items
- scripts/fetch.py pool address was using .strip("0x") — FIXED in Sprint 22B (use [2:] instead)
- scripts/fetch.py _COINGECKO_IDS hardcoded to 4 symbols (WETH, USDC, USDT, cbBTC) — extend when adding new pools
- scripts/run_backtest.py has no test coverage — manual validation only
- data/historical/ and data/prices/ are gitignored — must re-fetch after clean clone
- First real backtest run not yet executed — pending fetch + run_backtest execution
- scripts/fetch.py rewritten for GeckoTerminal OHLCV source.
   Fetch order: tokens first, pools second.
   8s rate limit sleep between pools, 2s between pagination pages within a pool (GeckoTerminal free tier = 30 req/min).
   OHLCV fetch paginates backwards using before_timestamp (1000 candles/page max) to support >90d.
   FETCH SUMMARY scoped to registry pairs only — shows OK/EMPTY/MISSING status per pool.

## Next Actions — YOU RUN (in order)
# 1. Fetch fresh data (now with DeFiLlama TVL history)
python scripts/fetch.py --days 90

# Watch for log lines like:
#   DeFiLlama TVL history: WETH-USDC-5 — 89 daily points
# If a pool shows 0 daily points it will use GT scalar fallback.

# 2. Re-run 90-day backtest
python scripts/run_backtest.py --days 90

# Expected corrected results:
#   WETH-USDC-5 fees: ~$800-$1,200 (was $6,529)
#   WETH-USDC-5 final_capital: ~$9,800-$10,200 (net of WETH depreciation)
#   This is the economically honest result.

# 3. Run trend module tests (from Sprint 26B)
python -m pytest tests/test_trend.py -v
