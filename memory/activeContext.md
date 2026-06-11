# Active Context

## Sprint 33 — Populate Registry from Pool Reference (COMPLETE)
- **Date**: 2026-06-10
- **Goal**: Populate registry/registry.json from memory/pool_reference.json with ALL active CL pools.
- **Selection criteria**: No TVL filter, no volume filter, all fee tiers included, gauge_alive must be true, CL only.
- **Result**: 268 pools written to registry/registry.json (32 existing merged verbatim, 236 new added).
  - Fee tier breakdown: 100(2), 500(1), 3000(185), 10000(63), plus exotic tiers (2700, 2800, 6000, 6900, 7000, 8000, 9000)
- **Merge logic**: Existing registry entries preserved verbatim by pool_address (lowercase match). New pools constructed from pool_reference data.
- **Scripts**: scripts/populate_registry.py rewritten for no-filter mode with merge logic.
  - Supports --dry-run CLI flag
  - Atomic write via tempfile + os.replace
  - Post-write validation (json.load verify) before exit
  - TOKEN_DECIMALS lookup table; unknown tokens default to 18
  - tick_lower/tick_upper: full-range [-887272, 887272] for all new entries
- **in_registry sync**: build_pool_reference.py re-run → 268/268 active pools show [IN REGISTRY].
- **Registry JSON resolved**: Pre-existing malformed JSON issue eliminated by full rebuild.

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

## Current Sprint: 26 patch (complete — awaiting YOU RUN)
- Sprint 26A: Mark-to-market capital fix. Added mark_to_market_usd() to core/il.py.
- Sprint 26B: Price trend awareness module. Created strategy/trend.py with 5 functions.
- Sprint 26 Patch: Fixed two fee calculation bugs (divisor + TVL scalar).

## Current Sprint: 25 (complete)
- Sprint 25: Added --days CLI flag to scripts/run_backtest.py. max_hold_hours = days * 24. run_id format: real_YYYY-MM-DD_Nd. (commit 6684695)

## Current Sprint: 24 (complete — awaiting YOU RUN)
- Sprint 24: Expanded registry to 5 pools (added WETH-USDC-30, cbBTC-USDC-5). Fixed WETH-cbBTC + USDC-USDT tick ranges to full range [-887272, 887272]. Ready for 90-day backtest.
- Sprint 24 Patch: Paginated GeckoTerminal OHLCV fetch (before_timestamp walks backwards in 1000-candle pages). Dedup at page boundaries.

## Current Sprint: 23 (complete — awaiting YOU RUN)
- Sprint 23: Fetch real TVL from GeckoTerminal pool info endpoint. Scalar per pool, current snapshot applied to all hourly records. Reverted evaluator.py TVL=0 guard. (commit TBD).

## Sprint 22 Goals
- Fix load_run_summary() root_path param (DONE — Sprint 22A, commit 619a201)
- Rewrite scripts/fetch.py to fetch directly from The Graph + CoinGecko (DONE — commit 73632d9)
- Write scripts/run_backtest.py one-shot runner (DONE — commit 73632d9)
- Fix scripts/fetch.py pool address strip bug (DONE — Sprint 22B)

## What Works Now
- E2E smoke test suite passes (tests/test_e2e_backtest.py — 15 tests)
- Registry fully populated: 268 active CL pools from Aerodrome Sugar SDK.
- scripts/fetch.py uses GeckoTerminal OHLCV as primary source.
- Mark-to-market capital fix + trend awareness integrated.

## Known Issues / Watch Items
- scripts/fetch.py _COINGECKO_IDS hardcoded to 4 symbols (WETH, USDC, USDT, cbBTC) — extend when adding new pools from expanded registry
- scripts/run_backtest.py has no test coverage — manual validation only
- data/historical/ and data/prices/ are gitignored — must re-fetch after clean clone

## Next Actions — YOU RUN (in order)
# 1. Fetch fresh data for expanded registry (now 268 pools)
python scripts/fetch.py --days 90

# 2. Re-run 90-day backtest
python scripts/run_backtest.py --days 90