System Patterns
Architecture: Seven-Layer Stack
Layer 1 registry/ Pool + token metadata. Dependency graph for pricing.
Layer 2 oracle/ Stateful price resolution. Graph-walk, no hardcoding.
Layer 3 historical/ Typed tick data loader. Real feeGrowthGlobal.
Layer 4 fetcher/ The Graph queries + post-fetch validation.
Layer 5 lp_math/ Pure stateless LP math functions.
Layer 6 backtest/ Thin orchestration. Consumes layers 2+3+5.
Layer 7 tests/ Pytest suite. One file per layer.

Key Patterns
None over Zero
get_usd_price() returns Optional[Decimal].
Never returns 0.0. Callers must handle None with explicit skip logic.

String Precision for uint256
feeGrowthGlobal fields stored as strings in JSON.
Never coerce to float. Parse as int() only when computing deltas.

Wrap-aware Fee Deltas
delta = new_fg - old_fg
if delta < 0: delta += 2**256 # handle 256-bit wrap

Registry as Single Source of Truth
Pool addresses live only in registry/registry.json.
No other file hardcodes an address.

Pure Math Layer
lp_math/ functions have zero side effects and zero external imports.
Accepts Decimal or int arguments only. All logic unit-testable.

Anchor Pool Loading
Backtest always loads anchor pools (pools needed to price WETH in USD)
regardless of --pool_filter CLI argument.
registry.get_anchor_pools() returns the required set.

Dependency-Order Price Resolution
PriceOracle resolves token prices in topological order from the dependency
graph declared in registry.json.
USDC/USDT = 1.0 (anchors, no resolution needed)
WETH resolved from WETH/USDC pool close
VIRTUAL resolved from VIRTUAL/WETH close * price_WETH
No special-casing per token symbol.

Module Dependency Rules (enforced)
lp_math -> no internal imports
historical -> registry only
oracle -> registry only
fetcher -> registry only
backtest -> oracle, historical, lp_math, strategy
strategy -> lp_math, registry
tests