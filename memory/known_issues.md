# Known Issues

_Last updated: Sprint 9_

## data/fetcher/gecko_terminal.py
- tvl_usd remains a snapshot from pool detail endpoint at fetch time, not historical per-candle TVL.
- fee_growth_global fields always None — exact fee attribution still deferred.
- price_token1_in_token0 uses candle close price, not true tick-level price.

## data/fetcher/token_prices.py
- CoinGecko token history is token-level USD pricing, not pool-execution pricing.
- Hourly resolution may be approximate for long date ranges depending on provider granularity.
- Symbol-based coin ID mapping is static and may require manual additions for new tokens.

## data/fetcher/coingecko.py
- Returns PoolDayData (daily-bucketed) for backward compatibility. Sprint 9 introduced TokenHistoryPoint via TokenPriceFetcher instead.

## data/loader/pool_loader.py
- save_pool_history accepts both PoolDayData and PoolHistoryPoint but the JSON wrapper key is always "days" for backward compatibility even when storing hourly points.

## backtest/
- Simulator still consumes PoolDayData. Migration to PoolHistoryPoint (hourly) is deferred until Sprint 10+.

## strategy/
- Scorer and signals modules do not yet consume TokenHistoryPoint data. Token trend detection will be implemented in Sprint 10.

## fee attribution
- Current fee attribution remains proportional-model based (core/fees.py).
- feeGrowthGlobal-based exact fee attribution is deferred to a future sprint.