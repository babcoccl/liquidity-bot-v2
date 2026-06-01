Tech Context
Environment
OS: Windows (primary) + Ubuntu 24.04 (secondary)
Python: 3.11+
IDE: VS Code with Cline extension
LLM backend: LM Studio running Qwen3-27B locally
Version control: GitHub (github.com/babcoccl/liquidity-bot-v2)

Core Libraries
decimal stdlib -- all LP math uses Decimal, not float
dataclasses stdlib -- TickSnapshot, PoolConfig, PriceSnapshot, BacktestConfig
typing stdlib -- Optional, list, dict throughout
pathlib stdlib -- all file paths use Path objects
json stdlib -- historical data stored and loaded as JSON
pytest external -- unit test runner
requests external -- The Graph HTTP queries in fetcher/

Data Sources
The Graph (Aerodrome subgraph on Base) -- poolDayDatas entity
Fields used: date, volumeUSD, tvlUSD, token0Price, token1Price,
feeGrowthGlobal0X128, feeGrowthGlobal1X128
URL: confirm in EPIC-4 Step 4.1 audit

Historical Data Format
Directory: data/historical/
Filename: {pool_address_lowercase}.json
Top-level keys: pool_address, pair_name, days
Day entry keys: date (int), volumeUSD (str), tvlUSD (str),
token0Price (str), token1Price (str),
feeGrowthGlobal0X128 (str|null),
feeGrowthGlobal1X128 (str|null)

Registry Format
File: registry/registry.json
Each pool entry includes:
pool_address, pair_name, token0 {symbol, decimals},
token1 {symbol, decimals}, fee_tier,
price_reference {SYMBOL: {quote: SYMBOL, source_pool: address}}

Token Decimal Handling
All raw amounts divided by 10**decimals before LP math.
Stored as Decimal throughout. Never float.

Conventions
File names: snake_case

Class names: PascalCase

Constants: UPPER_SNAKE_CASE

All public functions have type annotations

No bare except: clauses -- catch specific exceptions