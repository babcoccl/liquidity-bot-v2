Project Brief
Project
liquidity-bot-v2

Repository
github.com/babcoccl/liquidity-bot-v2 (to be created)

What This Is
A clean-room rearchitecture of an Aerodrome Finance LP harvesting and
backtesting system. The goal is a compartmentalized, unit-tested codebase
where each layer can be developed and verified in isolation.

Why v2 Exists
v1 (liquidity-bot) accumulated structural problems over 17 sprints that made
correctness impossible to verify:

Price resolution hardcoded and entangled with backtest harness

Fee growth synthesized from volume estimates, not real on-chain data

No unit tests for core math

900-line harness that cannot be reasoned about in parts

Primary Success Criterion
Run a backtest on any pool in registry.json and produce fee income and IL
numbers that match manually verified Uniswap V3 math, using real
feeGrowthGlobal snapshots from The Graph.

Secondary Goals
Every layer independently testable with pytest

Adding a new pool requires only a registry.json edit

Price resolution never returns 0.0 silently

Out of Scope (v2)
Live trading / on-chain execution

Email reporting

Dashboard UI
These may be added in v3 once the core math is correct.