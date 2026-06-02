# Test Coverage Map
_Last updated: Sprint 4_

| Module | File | Test File | Coverage | Missing / Notes |
|---|---|---|---|---|
| core.il | core/il.py | tests/test_scaffold.py | full | V3 concentrated range formula, Decimal throughout (Sprint 3 rewrite) |
| core.fees | core/fees.py | tests/test_scaffold.py | full | All functions tested including edge cases |
| core.metrics | core/metrics.py | tests/test_scaffold.py | full | All metrics functions tested with edge cases |
| core.models | core/models.py | tests/test_scaffold.py | full | PoolDayData construction and frozen test |
| strategy.scorer | strategy/scorer.py | tests/test_scaffold.py | partial | Score and normalize tested; weight loading from config not tested |
| strategy.signals | strategy/signals.py | tests/test_scaffold.py | partial | All signal classes have basic tests; edge cases for momentum crash with real history not covered |
| strategy.regime | strategy/regime.py | tests/test_scaffold.py | partial | Basic classify tested; boundary conditions between regimes not exhaustively tested |
| backtest.simulator | backtest/simulator.py | tests/test_scaffold.py | full | Position, BacktestSimulator enter/exit/step/summary all tested |
| backtest.multipool | backtest/multipool.py | none | none | No dedicated tests; MultiPoolBacktest class not directly tested |
| execution.base_executor | execution/base_executor.py | tests/test_scaffold.py | full | NotImplementedError raised for mint (all methods are stubs) |
| reporting.run_report | reporting/run_report.py | tests/test_scaffold.py | full | generate_run_report, format_position_line, save_report all tested |
| data.fetcher.base | data/fetcher/base.py | tests/test_scaffold.py + tests/test_data_layer.py | full | AbstractFetcher cannot instantiate; RateLimitError/FetchError hierarchy tested |
| data.fetcher.the_graph | data/fetcher/the_graph.py | tests/test_data_layer.py | full | Pagination, fee growth null handling, 429/500 errors all tested |
| data.fetcher.coingecko | data/fetcher/coingecko.py | tests/test_data_layer.py | partial | fetch_token_history tested; fetch_pool_history raises FetchError (by design) |
| data.fetcher.defillama | data/fetcher/defillama.py | tests/test_data_layer.py | full | TVL parsing, zero price fields, fee growth None, 429 error all tested |
| data.fetcher.router | data/fetcher/router.py | tests/test_data_layer.py | full | Fallback on RateLimitError, skip unavailable, all-exhausted error all tested |
| data.loader.pool_loader | data/loader/pool_loader.py | tests/test_data_layer.py | full | V1/V2 format loading, roundtrip save/reload, zero-volume skip, date sorting all tested |
| registry.types | registry/types.py | tests/test_registry.py | full | PoolConfig, TokenConfig, PriceReference frozen dataclasses |
| registry.registry | registry/registry.py | tests/test_registry.py | full | load, get, all, is_loaded, validate all tested |
| registry.__init__ | registry/__init__.py | tests/test_registry.py | full | Exports verified via import smoke test |
