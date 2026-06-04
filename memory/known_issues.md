# Known Issues

_Last updated: Sprint 9 Hotfix 2_

## data/fetcher/gecko_terminal.py
- tvl_usd remains a snapshot from pool detail endpoint at fetch time, not historical per-candle TVL.
- fee_growth_global fields always None — exact fee attribution still deferred.
- price_token1_in_token0 uses candle close price, not true tick-level price.
- HTTP 401 from GeckoTerminal indicates free-tier 180-day limit exceeded.
  Raises RateLimitError so FetchRouter falls through to TheGraph.
  TheGraph has no day cap with a valid API key.
  Pools with start dates within 180 days will be served by GeckoTerminal normally.

## data/fetcher/token_prices.py
- CoinGecko token history is token-level USD pricing, not pool-execution pricing.
- Hourly resolution may be approximate for long date ranges depending on provider granularity.
- Symbol-based coin ID mapping is static and may require manual additions for new tokens.

## data/fetcher/coingecko.py
- Now returns PoolHistoryPoint with hourly timestamps synthesized from daily source data.

## Sprint 9 Hotfix 2

### data/fetcher/the_graph.py / coingecko.py / defillama.py
- Fallback fetchers return synthesized hourly PoolHistoryPoint records
  expanded from daily source data (24 records per day, volume divided by 24).
- Price is constant within each synthesized day — no intraday movement.
  Backtester should be aware that hourly price variation only exists in
  GeckoTerminal-sourced records, not fallback-sourced records.

### data/fetcher/token_prices.py
- market_chart_range is CoinGecko Pro only. Replaced with market_chart
  free-tier endpoint using days + interval=hourly parameters.
- max lookback on free tier with interval=hourly is 90 days.
  Beyond 90 days, CoinGecko returns daily granularity regardless of
  interval parameter. Token history beyond 90 days will be daily-expanded.

### data/fetcher/gecko_terminal.py
- _INTER_POOL_SLEEP increased to 30s to reduce server-side 429 frequency
  across sequential pool fetches.

## data/loader/pool_loader.py
- save_pool_history accepts both PoolDayData and PoolHistoryPoint but the JSON wrapper key is always "days" for backward compatibility even when storing hourly points.

## backtest/
- Simulator still consumes PoolDayData. Migration to PoolHistoryPoint (hourly) is deferred until Sprint 10+.

## strategy/
- Scorer and signals modules do not yet consume TokenHistoryPoint data. Token trend detection will be implemented in Sprint 10.

## fee attribution
- Current fee attribution remains proportional-model based (core/fees.py).
- feeGrowthGlobal-based exact fee attribution is deferred to a future sprint.

## strategy/evaluator.py (Sprint 12)
- ExitReason.PRICE_OUT_OF_RANGE is defined but evaluate_position() never triggers it.
  tick_lower and tick_upper are stored on Position but tick-to-price conversion
  and range check are not implemented. Deferred to Sprint 13.

## backtest/harness.py (Sprint 12)
- _simulate_pool_hourly() returns total_fees_earned=Decimal("0").
  Fee attribution (proportional lp_fee_share) over the hourly path is deferred to Sprint 13.
- Position is constructed with tick_lower=-887272, tick_upper=887272 (full-range sentinel).
  Real tick ranges from pool registry metadata are not wired yet.
- days_simulated in BacktestResult now counts hours (not days) when the hourly path runs.
  BacktestReporter is not yet aware of this semantic shift.
