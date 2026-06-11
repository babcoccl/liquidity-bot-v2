# Active Context

## Sprint 33 — Populate Registry from Pool Reference (COMPLETE)
- **Date**: 2026-06-10
- **Goal**: Populate registry/registry.json from memory/pool_reference.json.
- **Selection criteria confirmed with user**:
  - TVL >= $100,000 (aggressive threshold)
  - Fee tiers: 0.05% / 0.3% / 1% (bps=5/30/100); excludes 0.01% stable-only and exotic tiers
  - 24h volume >= $10,000 (p25 of active-volume pools in the $100k+ TVL cohort)
- **Result**: 32 pools written to registry/registry.json.
  - 0.3% tier: 18 pools
  - 1% tier: 13 pools
  - 0.05% tier: 1 pool
- **Registry JSON fixed**: Pre-existing malformed JSON in registry.json (missing closing brace on USDC-USDT-1 entry) was eliminated by full rebuild.
- **Scripts added**: scripts/populate_registry.py
  - Supports --dry-run, --min-tvl, --min-vol CLI flags
  - Atomic write via tempfile + os.replace
  - Post-write validation (json.load verify) before exit
  - TOKEN_DECIMALS lookup table; unknown tokens default to 18
  - tick_lower/tick_upper: full-range [-887272, 887272] baseline for all entries
- **Next required step**: Run `python3 scripts/build_pool_reference.py` to update in_registry counts in pool_reference.json/pool_reference.md. Expected: in_registry should change from 0/268 to 32/268.
- **Note on prior 5-pool registry**: The 5 manually-curated pools from Sprints 22-24 (WETH-USDC-5, WETH-USDC-30, cbBTC-USDC-5, WETH-cbBTC-5, USDC-USDT-1) are included in the 32 if they meet criteria. USDC-USDT-1 (fee_bps=1, 0.01% tier) is excluded by fee tier filter — this is intentional.

## YOU RUN — Required after Sprint 33 commit
```bash
# 1. Verify registry JSON is valid
python3 -c "import json; data=json.load(open('registry/registry.json')); print(f'VALID — {len(data)} pools')"

# 2. Update in_registry counts in pool_reference
python3 scripts/build_pool_reference.py
# Expected: in_registry counts go from 0/268 to 32/268 in pool_reference.md

# 3. Verify pool_reference.md header shows 32 in_registry
head -20 memory/pool_reference.md
```

## Sprint 33-Pre — Aerodrome Pool Registry via Sugar SDK (complete)
- Replaced all Playwright/JS scraping with velodrome-finance/sugar-sdk.
- One `chain.get_pools()` call returns every pool field needed (pool address, gauge address, TVL, volume, fees, APR, tick spacing, token addresses) as typed Python objects.
- Sugar SDK `type == -1` identifies Concentrated Liquidity (Slipstream CL) pools.
- `gauge.alive == False` identifies migrating pools (superseded by newer pool).
- Symbol contains "migrat" as fallback migrating indicator.
- Fee tier mapped from tick_spacing: 1→0.01%, 50/100→0.05%, 200→0.3%, 2000→1%.
- Results: 268 active CL pools, 26951 migrating, 6555 basic excluded.
- Deleted: scripts/aero_extract.js (already absent: scrape_aerodrome_playwright.py, scrape_aerodrome_all.py)
- Added: scripts/fetch_aerodrome_pools.py, memory/pool_reference_raw.json, memory/pool_reference.json, memory/pool_reference.md
- build_pool_reference.py cross-references with registry.json (registry.json currently has invalid JSON — pre-existing issue).

## Sprint 32 — Consolidate DeFiLlama TVL to Single Path (implemented — awaiting YOU RUN)
- **Path 1 fix**: `fetch_defillama_tvl_history()` chart loop used `int(entry.get("timestamp", 0))` but DeFiLlama returns `"date"` as ISO string. Replaced with `_parse_defillama_ts(entry.get("date") or entry.get("timestamp") or 0)`.
- **Path 2 fix**: Eliminated redundant `_fetch_defillama_tvl_series()` path entirely. That function used 8-char truncated UUIDs from `_POOL_UUIDS` causing HTTP 400 on `yields.llama.fi/chart/{pool_uuid}` which requires full UUIDs. Now `tvl_history` dict from `fetch_defillama_tvl_history()` is passed directly into `fetch_pool_hourly()` via existing `tvl_history` param.
- Removed `pool_uuid: str = ""` parameter from `fetch_pool_hourly()` — no longer needed.
- Removed `pool_uuid = _POOL_UUIDS.get(...)` line and `pool_uuid=` kwarg from `main()`.
- `_POOL_UUIDS` dict retained for reference but no longer used in fetch path.

## Sprint 31 — Three Targeted Fixes (complete — awaiting YOU RUN re-fetch)
1. **DeFiLlama ISO date parse** — Added `_parse_defillama_ts()` helper in `scripts/fetch.py` to handle both Unix int/float and ISO 8601 string formats from DeFiLlama API. Replaced `int(entry["date"])` with `_parse_defillama_ts(entry["date"])`.
2. **END_OF_DATA exit reason** — Added `END_OF_DATA = auto()` to `ExitReason` enum in `strategy/exit_signal.py`. Added fallback `ExitSignal` after the main loop in `_simulate_pool_hourly` (`backtest/harness.py`) so simulations that exhaust all records get a proper exit reason instead of `None`.
3. **Annualized mean_fee_apr** — Replaced flat `total_fees / (capital * pools)` formula in `backtest/reporter.py` with annualized average of per-pool realized APRs: `mean((fees/capital) * 8760 / hours)`.

## Sprint 30 — TVL Historical Fix (implemented — awaiting YOU RUN)
- Replaced flat TVL scalar with per-timestamp historical TVL from DeFiLlama.
- Added `_interpolate_tvl()` helper: linearly interpolates between daily DeFiLlama snapshots for each hourly record.
- Added `_fetch_defillama_tvl_series()`: fetches daily TVL history via `yields.llama.fi/chart/{pool_uuid}`.
- Added `_POOL_UUIDS` map with 4 pool UUIDs (WETH-USDC-5, WETH-USDC-30, WETH-cbBTC-5, cbBTC-USDC-5).
- `fetch_pool_hourly()` now accepts `pool_uuid` param; applies interpolation when series is non-empty.
- Fallback to GT scalar if DeFiLlama returns empty or pool_uuid is missing.
- Uses `dataclasses.replace()` for immutable PoolHistoryPoint updates.

## Sprint 29 Hotfix (complete)
- Removed broken post-loop capital rescaling block from backtest/harness.py.
- Sprint 29 had introduced mutation of frozen BacktestResult fields
  (total_fees_earned, il_cost, etc.) using *= operator → FrozenInstanceError crash.
- Reverted _simulate_pool_hourly to signature with no capital parameter.
- Method now uses self.config.initial_capital directly as working capital.
- Per-pool capital normalization lives in reporter.py only (correct single source of truth).
- TVL flat-line (all records same value) remains open — next critical fix after this hotfix.

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
- scripts/fetch.py _COINGECKO_IDS hardcoded to 4 symbols (WETH, USDC, USDT, cbBTC) — extend when adding new pools from expanded registry
- scripts/run_backtest.py has no test coverage — manual validation only
- data/historical/ and data/prices/ are gitignored — must re-fetch after clean clone
- First real backtest run not yet executed — pending fetch + run_backtest execution
- scripts/fetch.py rewritten for GeckoTerminal OHLCV source.
   Fetch order: tokens first, pools second.
   8s rate limit sleep between pools, 2s between pagination pages within a pool (GeckoTerminal free tier = 30 req/min).
   OHLCV fetch paginates backwards using before_timestamp (1000 candles/page max) to support >90d.
   FETCH SUMMARY scoped to registry pairs only — shows OK/EMPTY/MISSING status per pool.

## Next Actions — YOU RUN (in order)
# 1. Validate registry JSON
python3 -c "import json; data=json.load(open('registry/registry.json')); print(f'VALID — {len(data)} pools')"

# 2. Update in_registry counts
python3 scripts/build_pool_reference.py

# 3. Fetch fresh data for expanded registry (now 32 pools)
python scripts/fetch.py --days 90

# 4. Re-run 90-day backtest
python scripts/run_backtest.py --days 90
