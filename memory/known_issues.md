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

## scripts/fetch.py — Switched to GeckoTerminal (Sprint 22E)
- The Graph decentralized network indexers for all Uniswap V3 Base
  subgraphs returned "Odd number of digits" errors on 2026-06-09.
  Both BuildersDAO (HMuAwufqZ1...) and community (96eJ9G...) subgraphs
  were affected simultaneously — infrastructure-level degradation.
- Switched primary data source to GeckoTerminal OHLCV REST API.
  No API key required. Free tier supports up to 6 months history.
  Rate limit: 30 req/min.
- TVL is not available per-candle from GeckoTerminal free tier.
  tvl_usd=0 in all PoolHistoryPoint records from this source.
  evaluator.py TVL_DECAY check patched to skip when tvl_usd=0.
  Real TVL fetch from GT pool info endpoint deferred to Sprint 23.
- Price source: GeckoTerminal OHLCV close price with token="base"
  gives price_token1_in_token0 directly. CoinGecko USD price
  sanity check removed (Sprint 22E Patch 3, commit 1a461a5) because
  it compared GT ratio (e.g., cbBTC/WETH ≈ 0.047) against
  CoinGecko USD/USD (e.g., cbBTC_usd/WETH_usd ≈ 24) — different
  quantities for non-stablecoin pairs. Only valid when both tokens
  are USD-denominated, which never occurs for ratio prices.
- Empty-file guard: when fetch_pool_hourly returns 0 records, an
  explicit empty records file is written atomically to prevent the
  FETCH SUMMARY from reading stale files from prior runs.
- feeGrowthGlobal not available. fee_growth_global_0/1 = None.
  Fee accumulation in harness uses volume_usd * fee_rate (unaffected).
- THEGRAPH_API_KEY is now optional — fetch.py will not exit if missing.
  Key retained in env for future Graph fallback use.
- WATCH Sprint 23: Add TVL fetch from GT pool info endpoint.
  Endpoint: GET /networks/base/pools/{address}
  Field: data.attributes.reserve_in_usd

## fetch.py — TVL now real from GT pool info endpoint (Sprint 23)
- Sprint 22E tvl_usd=0 workaround replaced with real TVL from
  GeckoTerminal GET /networks/base/pools/{address} endpoint.
  Field: data.attributes.reserve_in_usd (current TVL as string).
- TVL is a scalar (current snapshot) applied to all hourly records.
  Historical per-record TVL requires paid GT tier — deferred Sprint 24.
- evaluator.py TVL_DECAY guard reverted to simple tvl < min_tvl_usd.
- Rate limit: +1 req per pool per fetch run. Total requests per run:
    4 CoinGecko (tokens) + 3 OHLCV + 3 pool info = 10 req per run.
    With 1s+3s sleeps, total wall time ~25s. Well within 30 req/min.
- WATCH Sprint 24: per-candle TVL from GT paid OHLCV endpoint
  (includes volume and liquidity per candle in Pro tier).

## registry/registry.json — Expanded to 5 pools (Sprint 24)
- Added WETH-USDC-30 (0.3% fee, $96.8M TVL, $101M/day vol)
  and cbBTC-USDC-5 (0.05% fee, $9.1M TVL, $124M/day vol).
  Both discovered via GeckoTerminal search API on 2026-06-09.
- Fixed WETH-cbBTC tick range [-2000,2000] → [-887272,887272].
  Tight range caused 0 fee earnings across 30d — pool was
  out of range the entire backtest window.
- Fixed USDC-USDT tick range [-50,50] → [-887272,887272].
- All pools now use full-range ticks as conservative baseline.
  Concentrated range optimization deferred to Sprint 25.
- pair_name convention updated: {TOKEN0}-{TOKEN1}-{FEE_BPS}
  where FEE_BPS = fee_tier / 100 (e.g. 500 → 5, 3000 → 30).
- WATCH Sprint 25: Add concentrated tick range per pool based
  on 90d realized volatility (±2σ price band).

## Sprint 26 — Mark-to-market + trend awareness

### Mark-to-market fix (Part A)
- Prior to Sprint 26, final_capital ignored USD price changes
  of the volatile token leg. A 20% WETH drop on a 50/50 position
  reduced actual value by ~$1,000 but backtest showed $10,000 base.
- Fix: mark_to_market_usd() in core/il.py. Applied in harness
  final_capital calculation using token0 USD price at entry and exit.
- New result field: mtm_adjustment (signed USD). Appears in summary.json.
- Backtest results from Sprint 25 and earlier are overstated in
  bear markets, understated in bull markets. Re-run after this fix.

### Trend awareness (Part B)
- strategy/trend.py added with 5 functions:
    trend_strength(), trend_direction(), is_ranging(),
    trend_score_penalty(), should_exit_trend()
- trend_score_penalty() integrated into compute_pool_score().
  Trending pools score lower — less likely to pass entry gate.
- should_exit_trend() integrated into harness step loop.
  New exit reason: TREND_EXIT:<detail> (ExitReason.TREND_EXIT added).
- Thresholds (tunable in config):
    strength_threshold = 0.05 (entry penalty kicks in at 0.03)
    adverse_move_threshold = 0.07
- WATCH Sprint 27: Add trend_strength_threshold to BacktestConfig
  so it can be sweep-tuned. Current values are hardcoded defaults.

## Sprint 26 Patch — Fee calculation bugs fixed

### Bug 1: estimate_daily_fees() wrong fee divisor (minor)
- Used / 10,000 treating fee_tier as true BPS (500 = 5%).
- Correct: / 1,000,000 (Uniswap V3 units: 500 = 0.05%).
- Impact: only affects simulator.py path (PositionSimulator /
  BacktestSimulator). Harness uses net_lp_alpha_from_records()
  which was already correct. Fixed in core/fees.py.

### Bug 2: TVL scalar overstates fees 6× (critical)
- Current TVL snapshot ($8.55M) applied to all 90d records.
- Pool TVL was likely ~$50-60M in March 2026 — 6× higher.
- LP fee share = position/TVL, so lower historical TVL =
  lower fees. Using current (low) TVL overstates fee share.
- Fix: fetch per-day TVL from DeFiLlama yields chart API.
  Match to hourly records by nearest daily timestamp (±12h).
- Fallback: GT current TVL scalar if DeFiLlama has no data.
- Expected corrected 90d fee for WETH-USDC-5: ~$800-$1,200
  (vs $6,529 before fix). Consistent with DeFiLlama 44% APY.
- WATCH: DeFiLlama may not have all 5 pools indexed on Base.
  WETH-cbBTC-5 and cbBTC-USDC-5 may fall back to GT scalar.
