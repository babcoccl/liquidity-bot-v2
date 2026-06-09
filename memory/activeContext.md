# Active Context

## Current Sprint: 22D (complete — awaiting YOU RUN validation)

## Sprint 22 Goals
- Fix load_run_summary() root_path param (DONE — Sprint 22A, commit 619a201)
- Rewrite scripts/fetch.py to fetch directly from The Graph + CoinGecko (DONE — commit 73632d9)
- Write scripts/run_backtest.py one-shot runner (DONE — commit 73632d9)
- Fix scripts/fetch.py pool address strip bug (DONE — Sprint 22B)
- Update memory/activeContext.md (DONE — Sprint 22B)

## What Works Now
- E2E smoke test suite passes (tests/test_e2e_backtest.py — 15 tests)
- load_run_summary() accepts root_path param — xfail removed
- scripts/fetch.py rewrites pool history + token prices from live APIs
- scripts/run_backtest.py runs backtest on real data and writes results/runs/{run_id}/summary.json
- pool_loader.py atomic write consolidated for both hourly + daily branches
- registry/registry.json trimmed to 3 pools for first real data validation run

## Known Issues / Watch Items
- scripts/fetch.py pool address was using .strip("0x") — FIXED in Sprint 22B (use [2:] instead)
- scripts/fetch.py _COINGECKO_IDS hardcoded to 4 symbols (WETH, USDC, USDT, cbBTC) — extend when adding new pools
- scripts/run_backtest.py has no test coverage — manual validation only
- data/historical/ and data/prices/ are gitignored — must re-fetch after clean clone
- First real backtest run not yet executed — pending fetch + run_backtest execution
- scripts/fetch.py rewritten for Messari schema (Option B).
  Field: liquidityPoolHourlySnapshots. Price ratio derived from
  CoinGecko price index at fetch time (t1_usd / t0_usd).
  Fetch order: tokens first, pools second.

## Next Actions — YOU RUN (in order)
# 1. Verify endpoint + confirm liquidityPoolHourlySnapshots field
python scripts/check_graph_endpoint.py

# 2. Fetch 30 days (tokens first, then pools with price join)
python scripts/fetch.py --days 30

# 3. Verify all data files non-empty
python scripts/check_data_files.py

# 4. Run backtest
python scripts/run_backtest.py

# Paste === FETCH SUMMARY === and === BACKTEST SUMMARY === back
# for review. Collaborator will verify price ratio magnitudes
# before declaring Sprint 22D complete.
