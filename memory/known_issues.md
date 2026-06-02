# Known Issues
_Last updated: Sprint 3_

## strategy/scorer.py
- Weights hardcoded in class; not loaded from config/default.yaml scoring.weights
- `score()` returns 0.0 when any expected key missing from pool dict — silent failure

## strategy/signals.py
- MomentumCrashSignal uses float arithmetic for price change calculation
- TVLCollapseSignal threshold is fixed at -30% in default config; not adaptive per-pool

## strategy/regime.py
- Boundary conditions between regime classifications (e.g., exactly 0.5 volatility) may produce unexpected results
- No hysteresis — regime can flip rapidly on small input changes

## backtest/multipool.py
- MultiPoolBacktest class has no test coverage
- Capital allocation strategy not implemented (uses equal-weight placeholder)

## data/fetcher/coingecko.py
- `fetch_pool_history()` always raises FetchError with "token_id" message — only `fetch_token_history()` works
- TVL always returns Decimal("0") because CoinGecko has no pool-level TVL data

## No Issues Documented
- core/fees.py
- core/metrics.py
- core/models.py
- backtest/simulator.py
- execution/base_executor.py
- reporting/run_report.py
- data/fetcher/base.py
- data/fetcher/the_graph.py
- data/fetcher/defillama.py
- data/fetcher/router.py
- data/loader/pool_loader.py

## Resolved in Sprint 3
- **core/il.py** — Rewrote with Decimal and true V3 concentrated range formula. Previous issues: used float throughout, full-range AMM IL only (not V3 concentrated), tick_lower/tick_upper ignored.