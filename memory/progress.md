# Progress

## Completed

### Planning Phase
- [x] Identified root causes of v1 bugs (fee synthesis, price entanglement)
- [x] Defined seven-layer v2 architecture
- [x] Defined memory file pattern for Cline token efficiency
- [x] Wrote EPIC-4 implementation spec (fetch feeGrowthGlobal from Graph)
- [x] Wrote EPIC-4 Step 4.1 audit spec

### Sprint 1 — Foundation (COMPLETE)
- [x] Create github.com/babcoccl/liquidity-bot-v2 repository
- [x] Create directory scaffold
- [x] Create five memory files in memory/
- [x] core/models.py — PoolDayData frozen dataclass
- [x] data/fetcher/base.py — AbstractFetcher, RateLimitError, FetchError
- [x] Audit notes added to core/il.py, core/fees.py, core/metrics.py
- [x] Audit notes added to strategy/scorer.py, strategy/signals.py, strategy/regime.py
- [x] Audit notes added to backtest/simulator.py, backtest/multipool.py
- [x] .gitkeep files in data/historical/, results/, logs/
- [x] memory/techContext.md updated (Python 3.12, pip 24.0, CoinGecko, DeFiLlama)
- [x] config/default.yaml verified complete
- [x] Tests added to tests/test_scaffold.py (PoolDayData, AbstractFetcher, exceptions)

### Sprint 2 — Data Layer (COMPLETE)
- [x] data/fetcher/the_graph.py — TheGraphFetcher implementation
- [x] data/fetcher/coingecko.py — CoinGeckoFetcher implementation
- [x] data/fetcher/defillama.py — DeFiLlamaFetcher implementation
- [x] data/fetcher/router.py — FetchRouter with fallback chain
- [x] data/loader/pool_loader.py — PoolLoader with cache & pagination
- [x] tests/test_data_layer.py — all data layer tests
- [x] data/fetcher/__init__.py updated
- [x] data/loader/__init__.py updated

### Sprint 3 — Core Math Rewrite (COMPLETE)
- [x] memory/manifest.json — component manifest backfilled for all sprints
- [x] AUDIT: tags added to all implementation files
- [x] tests/coverage_map.md — created
- [x] memory/known_issues.md — created
- [x] core/il.py — rewritten with Decimal and true V3 concentrated range IL formula
- [x] tests/test_scaffold.py — IL tests updated for new API
- [x] memory/progress.md — stale pending entries purged

### Sprint 4 — Registry Layer (COMPLETE)
- [x] memory/manifest.json — sprint numbers corrected, status fixes applied
- [x] memory/known_issues.md — core/fees.py, core/metrics.py, backtest modules documented
- [x] registry/types.py — PoolConfig, TokenConfig, PriceReference frozen dataclasses
- [x] registry/registry.py — PoolRegistry with load, get, all, is_loaded, validate
- [x] tests/test_registry.py — 21 test cases, all passing
- [x] registry/__init__.py — exports wired
- [x] memory/manifest.json — Sprint 4 components added, last_updated_sprint: 4
- [x] tests/coverage_map.md — Sprint 4 rows added

### Sprint 5 — Fetch Entrypoint + Subgraph Verification (COMPLETE)
- [x] memory/known_issues.md — last_updated bumped to Sprint 4
- [x] config/default.yaml — data_sources block added (TheGraph URL, CoinGecko, DeFiLlama)
- [x] data/fetcher/validate_historical.py — ValidationError, validate_no_gaps, validate_no_negative_values, validate_price_sanity, validate_fee_growth_present, validate_all
- [x] scripts/fetch.py — CLI entrypoint wiring PoolRegistry → FetchRouter → save_pool_history → validate_all
- [x] tests/test_validate_historical.py — 19 test cases
- [x] memory/manifest.json — Sprint 5 components added, last_updated_sprint: 5
- [x] tests/coverage_map.md — Sprint 5 rows added

### Sprint 6 — Registry Population + Backtest Harness (COMPLETE)
- [x] config/default.yaml — stale legacy data: block removed
- [x] memory/progress.md — stale known risk removed
- [x] registry/registry.json — 15 pools populated from v1 data/registry.json
- [x] backtest/config.py — BacktestConfig frozen dataclass, from_yaml loader
- [x] backtest/reporter.py — BacktestResult, BacktestReporter, save(), print_summary()
- [x] backtest/harness.py — BacktestHarness, run(), _simulate_pool(), NotImplementedError fallback
- [x] scripts/backtest.py — CLI entrypoint wiring BacktestConfig → PoolRegistry → BacktestHarness
- [x] tests/test_backtest_harness.py — 12 test cases
- [x] memory/manifest.json — Sprint 6 components added, last_updated_sprint: 6
- [x] tests/coverage_map.md — Sprint 6 rows added

### Sprint 7 — API Keys, CoinGecko Datasource, Units Layer & Simulator (COMPLETE)
- [x] config/default.yaml — THEGRAPH_API_KEY, COINGECKO_API_KEY, BASE_RPC_HTTP/WS added
- [x] pyproject.toml — python-dotenv added to dependencies
- [x] data/fetcher/the_graph.py — api_key param, Authorization Bearer header, 401 handler
- [x] scripts/fetch.py — dotenv loader, THEGRAPH_API_KEY env var, registry_path to CoinGecko
- [x] data/fetcher/coingecko.py — fetch_pool_history implemented via COIN_ID_MAP + registry lookup
- [x] core/units.py — TaggedDecimal, DenominationError, MULTIPLY_RULES, convenience constructors
- [x] core/fees.py — migrated float → TaggedDecimal throughout
- [x] backtest/simulator.py — PositionSimulator.step() implemented, all float → TaggedDecimal
- [x] tests/test_units.py — ~30 test cases for TaggedDecimal denomination enforcement
- [x] tests/test_data_layer.py — CoinGecko pool tests added, TheGraph auth header tests added, old stub test removed
- [x] memory/known_issues.md — coingecko, fees, simulator sections updated; last_updated Sprint 7
- [x] memory/manifest.json — 5 components updated, 2 new components added, last_updated_sprint: 7

### Sprint 7 Hotfix — Simulator & Test Correctness (COMPLETE)
- [x] tests/test_units.py — match string fixed: "incompatible" → "Cannot apply"
- [x] backtest/simulator.py — Position.last_price field added; Position.update() records
      last seen price; BacktestSimulator.summary() uses last_price for IL computation
      instead of current_value/capital ratio
- [x] tests/test_simulator.py — new file, full coverage of Position, PositionSimulator,
      BacktestSimulator including regression test for IL price bug
- [x] memory/known_issues.md — hotfix note appended to backtest/simulator.py section
- [x] memory/manifest.json — backtest.simulator audit_notes updated; test file entry added

### Sprint 8 — Fetch Pipeline Repair (COMPLETE)
- [x] data/fetcher/gecko_terminal.py — GeckoTerminalFetcher (primary OHLCV source, matches v1 strategy)
- [x] data/fetcher/__init__.py — GeckoTerminalFetcher exported
- [x] data/fetcher/the_graph.py — FetchError now logs response body/errors; URL supports {api_key} path substitution
- [x] config/default.yaml — the_graph URL updated to decentralized gateway; gecko_terminal block added
- [x] scripts/fetch.py — GeckoTerminalFetcher wired as primary in FetchRouter; TheGraph URL key substitution applied
- [x] memory files updated

### Sprint 9 — Hourly History + Token Trend Layer (COMPLETE)
- [x] core/models.py — PoolHistoryPoint and TokenHistoryPoint added
- [x] data/fetcher/gecko_terminal.py — preserves hourly timestamps; no daily collapse
- [x] data/fetcher/token_prices.py — CoinGecko token history fetcher added
- [x] data/loader/pool_loader.py — hourly persistence supported
- [x] data/loader/token_loader.py — token history persistence added
- [x] data/fetcher/validate_historical.py — hourly gap validation added
- [x] scripts/fetch.py — fetches pool history plus token0/token1 history for same lookback window
- [x] tests updated
- [x] memory files updated

### Sprint 9 Hotfix — GeckoTerminal 401 Fallback (COMPLETE)
- [x] data/fetcher/gecko_terminal.py — HTTP 401 now raises RateLimitError
      so FetchRouter falls through to TheGraph for pools beyond 180-day free tier
- [x] tests/test_data_layer.py — 401 → RateLimitError test added
- [x] memory files updated

## In Progress
_(none)_

## Next Action: Sprint 10 — Strategy Signals Consume Token Trend + Hourly Pool Data

## Deferred (not in v2 scope)
