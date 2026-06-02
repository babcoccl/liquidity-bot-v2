# Active Context

**Current focus:** Sprint 8 — Backtest Validation Run + feeGrowthGlobal Fee Attribution

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 7 — API Keys, CoinGecko Datasource, Units Layer & Simulator
(core/units.py TaggedDecimal, core/fees.py migrated, PositionSimulator.step() implemented,
TheGraph API key support, CoinGecko fetch_pool_history via COIN_ID_MAP)

**Note:** PositionSimulator fee attribution uses proportional TVL model.
feeGrowthGlobal-based exact fee computation is deferred to Sprint 8.

**Note:** metrics.py still uses float — intentional. Sharpe/drawdown
operate on dimensionless return series. TaggedDecimal boundary crossing
in BacktestSimulator.summary() is explicit and commented.

**Note:** BASE_RPC_HTTP and BASE_RPC_WS are parked in config — not consumed until
execution modules are built.