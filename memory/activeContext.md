# Active Context

## Current Sprint: 22 (PARTIAL — in progress)

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

## Next Actions (Sprint 23)
- Run: python scripts/fetch.py --days 30
- Run: python scripts/run_backtest.py
- Review results/runs/real_{date}/summary.json
- Determine whether to expand registry back toward 15 pools or tune strategy params first