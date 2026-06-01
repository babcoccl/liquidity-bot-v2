Progress
Completed
[PLANNING] Identified root causes of v1 bugs (fee synthesis, price entanglement)

[PLANNING] Defined seven-layer v2 architecture

[PLANNING] Defined memory file pattern for Cline token efficiency

[PLANNING] Wrote EPIC-4 implementation spec (fetch feeGrowthGlobal from Graph)

[PLANNING] Wrote EPIC-4 Step 4.1 audit spec

In Progress
Create github.com/babcoccl/liquidity-bot-v2 repository

Create directory scaffold

Create five memory files in memory/

Interview user to confirm scope and first deliverable

Pending (ordered)
Layer 1: registry/types.py -- PoolConfig, TokenConfig dataclasses

Layer 1: registry/registry.py -- PoolRegistry class with dependency graph

Layer 1: tests/test_registry.py

Layer 5: lp_math/tick_math.py -- sqrt_price <-> tick conversions (pure)

Layer 5: lp_math/math.py -- inventory_amounts, fees_accrued, IL, position_value_usd

Layer 5: tests/test_lp_math.py

Layer 3: historical/types.py -- TickSnapshot dataclass

Layer 3: historical/loader.py -- HistoricalLoader class

Layer 3: tests/test_historical_loader.py

Layer 4: fetcher/fetch_pool_history.py -- add feeGrowthGlobal to query

Layer 4: fetcher/validate_historical.py -- post-fetch validation checks

Layer 2: oracle/price_oracle.py -- PriceOracle with graph-walk resolution

Layer 2: tests/test_price_oracle.py

Layer 6: backtest/harness.py -- thin orchestration (~300 lines)

Layer 6: backtest/config.py and backtest/reporter.py

Layer 6: tests/test_backtest_harness.py

End-to-end verification: one pool, known dates, match manual Uniswap V3 math

Deferred (not in v2 scope)
Live trading / on-chain execution

Email reporting

Dashboard UI

Multi-pool rotation optimizer

Known Risks
feeGrowthGlobal may not be available on the Aerodrome subgraph (verify in EPIC-4 Step 4.1)

v1 registry.json may need to be partially rebuilt for v2 price_reference