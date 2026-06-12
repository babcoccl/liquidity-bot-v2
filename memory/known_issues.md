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

### Bug 2: TVL scalar overstates fees 6× (critical) — STATUS: FIX IMPLEMENTED Sprint 30 — awaiting YOU RUN confirmation
- Current TVL snapshot ($8.55M) applied to all 90d records.
- Pool TVL was likely ~$50-60M in March 2026 — 6× higher.
- LP fee share = position/TVL, so lower historical TVL =
  lower fees. Using current (low) TVL overstates fee share.
- Sprint 30 fix: _fetch_defillama_tvl_series() fetches daily TVL history
  from yields.llama.fi/chart/{pool_uuid}. _interpolate_tvl() linearly
  interpolates per hourly record. Fallback to GT scalar if empty.
- Expected corrected 90d fee for WETH-USDC-5: ~$800-$1,200
  (vs $6,529 before fix). Consistent with DeFiLlama 44% APY.
- WATCH: After re-fetch, TVL range log must show first != last for all pools.

## scripts/fetch.py — TVL historical series via DeFiLlama (Sprint 30)
- fetch_pool_hourly now accepts pool_uuid param.
- _fetch_defillama_tvl_series fetches daily TVL history from yields.llama.fi.
- _interpolate_tvl linearly interpolates per hourly record from daily snapshots.
- Fallback to GT scalar if DeFiLlama returns empty or pool_uuid missing.
- _POOL_UUIDS map: WETH-USDC-5, WETH-USDC-30, WETH-cbBTC-5, cbBTC-USDC-5.
- Uses dataclasses.replace() for immutable PoolHistoryPoint updates.
- STATUS: IMPLEMENTED Sprint 30 — awaiting YOU RUN re-fetch confirmation.
- WATCH: After re-fetch, TVL range log must show first != last for all pools.

## backtest/harness.py — Post-loop capital rescaling removed (Sprint 29 Hotfix)
- Sprint 29 agent introduced post-loop mutation of frozen BacktestResult fields
  (total_fees_earned, il_cost, etc.) using *= operator.
- FrozenInstanceError crash on run. Fixed by removing rescaling block entirely.
- Per-pool capital normalization lives in reporter.py only (correct location).
- _simulate_pool_hourly reverted to no capital parameter; uses self.config.initial_capital directly.
- STATUS: RESOLVED Sprint 29 Hotfix.

## scripts/fetch.py — DeFiLlama date field ISO string not int (Sprint 31)
- _fetch_defillama_tvl_series used int(entry["date"]) but DeFiLlama
  returns ISO 8601 strings ('2023-12-03T23:05:17.943Z'), not Unix ints.
- Fix: _parse_defillama_ts() helper normalizes both formats.
- STATUS: RESOLVED Sprint 31.

## backtest/harness.py — null exit_reason when loop exhausts records (Sprint 31)
- When aligned records run out before max_hold_hours, exit_signal is None.
- Reporter skips null exit_reasons in counts. most_common_exit_reason wrong.
- Fix: END_OF_DATA fallback ExitSignal after loop in _simulate_pool_hourly.
- STATUS: RESOLVED Sprint 31.

## backtest/reporter.py — mean_fee_apr not annualized (Sprint 31)
- Aggregate mean_fee_apr used raw total_fees / initial_capital with no
  annualization factor. Fix: mean of per-pool (fees/capital)*(8760/hours).
- STATUS: RESOLVED Sprint 31.

## Sprint 33-Pre — Sugar SDK pool identification rules
- `type == -1` identifies Concentrated Liquidity (Slipstream CL) pools.
- `gauge.alive == False` identifies migrating pools (superseded by newer pool).
- Symbol string contains "migrat" as fallback migrating indicator.
- Fee tier mapped from tick_spacing: 1→0.01% (100 bps), 50/100→0.05% (500 bps), 200→0.3% (3000 bps), 2000→1% (10000 bps).
- Non-CL pools (Basic Volatile type=0, Basic Stable type=1) are excluded from registry.
- Sugar SDK uses Base RPC endpoint; set SUGAR_RPC_URI_8453 env var for production use.

## scripts/fetch.py — Two competing DeFiLlama TVL paths (Sprint 32)
- fetch_defillama_tvl_history() used int(entry["timestamp"]) but DeFiLlama
  chart API field is "date" (ISO string). Fixed with _parse_defillama_ts().
- _fetch_defillama_tvl_series() used 8-char truncated UUIDs causing HTTP 400.
  Eliminated entirely — tvl_history dict from fetch_defillama_tvl_history()
  passed directly into fetch_pool_hourly() via existing tvl_history param.
- pool_uuid param removed from fetch_pool_hourly(). _POOL_UUIDS map unused.
- STATUS: RESOLVED Sprint 32 — awaiting YOU RUN confirmation.

## registry/registry.json — Populated from pool_reference.json (Sprint 33)
- Registry was expanded from 32 manually-curated pools to 268 active CL pools
  using scripts/populate_registry.py. All pools from memory/pool_reference.json.
- Merge logic: existing 32 registry entries preserved verbatim by pool_address
  (lowercase match). Remaining 236 pools constructed from Sugar SDK data.
- No TVL or volume floor applied — all active CL pools included.
- tick_lower/tick_upper set to full-range [-887272, 887272] for new entries.
- Existing entries retain their manually-curated ticks and price_reference.

## Sprint 34 — On-chain price feed via Multicall3 slot0

### fetch_prices.py CoinGecko ID coverage
- _COINGECKO_IDS covers only tokens with known mappings. Pools where neither
  token has a CoinGecko ID will show price_status="no_usd_ref".
  Extend _COINGECKO_IDS as new pools are prioritized for active management.

### GeckoTerminal dropped from architecture
- check_geckoterminal.py retained in repo as diagnostic only.
- GT rate limit (30 req/min free tier) is incompatible with bot cycle time.
- On-chain slot0 via Multicall3 replaces GT for real-time price feeds.

## registry/registry.json — fee_tier values incompatible with validator (Sprint 37)
- PoolRegistry.validate() rejects fee_tier not in {100, 500, 3000, 10000}.
- Most pools in registry.json have fee_tier=50000 (0.05%), 300000 (3%), or other
  values that use Uniswap V3's native units (fee = fee_tier / 1_000_000).
- This causes run_pool_scan.py to exit code 1 on registry validation failure.
- Root cause: populate_registry.py mapped tick_spacing→fee_tier using
  values like 50000, 300000 instead of BPS-style {100, 500, 3000, 10000}.
- Two options to resolve:
  (A) Normalize registry fee_tier to {100, 500, 3000, 10000} and keep validator as-is.
  (B) Expand validator's _VALID_FEE_TIERS to include {50000, 300000, 1000000}.
- Option A preferred: aligns with Uniswap V3 convention where fee_tier is
  expressed in basis-points-of-a-million (e.g. 3000 = 0.3%).
- STATUS: BLOCKING Sprint 37 completion. Registry must be cleaned before pool_scan can produce output.
