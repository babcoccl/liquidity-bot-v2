# Known Issues
_Last updated: Sprint 8_

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
- No test coverage
- Uses float for all financial math
- Capital allocation uses equal-weight placeholder, not config-driven

## core/fees.py
- Migrated to TaggedDecimal in Sprint 7 — float issues resolved.
- fee_gas_ratio returns RATIO("0") when gas_cost is 0 instead of float("inf").
  Callers must check gas_cost_usd.value <= 0 before calling if they need to
  detect the zero-gas case.

## core/metrics.py
- Uses float throughout for all financial math — must migrate to Decimal

## backtest/simulator.py
- Uses TaggedDecimal throughout for all financial math (Sprint 7 complete).
- PositionSimulator.step() is now implemented — accepts PoolDayData, no longer raises NotImplementedError.
- fee attribution uses estimate_daily_fees → lp_fee_share proportional model.
  Does not use feeGrowthGlobal — that is deferred to a future sprint.
- price_lower/upper set as entry_price × multiplier (default ±10%).
  Config-driven range width is deferred.
- HOTFIX Sprint 7: summary() previously computed current_price as
  current_value_usd / capital_usd (a ratio, not a price), producing
  incorrect IL. Fixed by storing last_price on Position and using it
  in summary(). Regression test: test_summary_il_uses_last_price_not_value_ratio.

## data/fetcher/coingecko.py
- fetch_pool_history() resolves pool→token via registry lookup + COIN_ID_MAP static table.
  Requires registry_path to be accurate at instantiation. Pools with tokens not in
  COIN_ID_MAP raise FetchError — add symbol to COIN_ID_MAP as needed.
- TVL always returns Decimal("0") — CoinGecko has no pool-level TVL data.
- fee_growth_global fields always None — CoinGecko cannot provide.
- price_token1_in_token0 is token1's USD price (proxy only — not true intra-pool
  price ratio for non-USD pairs).

## data/fetcher/gecko_terminal.py
- tvl_usd is a snapshot from pool detail endpoint at fetch time, not per-candle historical TVL.
  All PoolDayData records for a pool in a single fetch share the same tvl_usd value.
- fee_growth_global fields always None — GeckoTerminal cannot provide.
  Backtest fee attribution will use proportional TVL model when this fetcher is primary source.
- price_token1_in_token0 uses candle close price — not a true intra-pool tick price.
- Hourly candles bucketed to UTC midnight for daily date field. Multiple candles per day
  collapse to the last candle's close (dedup by date keeps last).

## No Issues Documented
- core/models.py
- core/units.py
- execution/base_executor.py
- reporting/run_report.py
- data/fetcher/base.py
- data/fetcher/the_graph.py
- data/fetcher/defillama.py
- data/fetcher/router.py
- data/loader/pool_loader.py

## Resolved in Sprint 3
- **core/il.py** — Rewrote with Decimal and true V3 concentrated range formula. Previous issues: used float throughout, full-range AMM IL only (not V3 concentrated), tick_lower/tick_upper ignored.