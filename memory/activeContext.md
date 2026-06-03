# Active Context

**Current focus:** Sprint 9 — Backtest Validation Run + feeGrowthGlobal Fee Attribution

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 8 — Fetch Pipeline Repair
GeckoTerminalFetcher added as primary source (matches v1 strategy).
FetchRouter order: GeckoTerminal → TheGraph → CoinGecko → DeFiLlama.
TheGraph URL updated to decentralized gateway with {api_key} path substitution.
TheGraphFetcher FetchError now logs full response body on unexpected structure.

**Note:** PositionSimulator fee attribution uses proportional TVL model.
feeGrowthGlobal-based exact fee computation is deferred to Sprint 9.

**Note:** GeckoTerminal tvl_usd is a single snapshot per pool per fetch run,
not per-candle historical TVL. Acceptable for current backtest fidelity.

**Note:** metrics.py still uses float — intentional. Sharpe/drawdown
operate on dimensionless return series. TaggedDecimal boundary crossing
in BacktestSimulator.summary() is explicit and commented.

**Note:** BASE_RPC_HTTP and BASE_RPC_WS are parked in config — not consumed until
execution modules are built.