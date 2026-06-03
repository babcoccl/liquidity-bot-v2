# Active Context

**Current focus:** Sprint 10 — Strategy Signals Consume Token Trend + Hourly Pool Data

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 9 — Hourly History + Token Trend Layer
Pool history now preserves hourly timestamps from GeckoTerminal.
Token price history is fetched separately from CoinGecko for both pool tokens.
Fetch script writes synchronized pool and token datasets for the same lookback period.

**Note:** feeGrowthGlobal-based exact fee attribution is still deferred.
Current fee attribution remains proportional-model based.

**Note:** GeckoTerminal tvl_usd remains a per-fetch snapshot, not historical hourly TVL.

**Note:** Token trend signals should use token_history datasets rather than infer token direction solely from pool price ratio.