Active Context
Current Focus
Project initialization. No code exists yet for liquidity-bot-v2.

Immediate Task
Interview user to confirm v2 goals, scope, and first deliverable.
Then create the repository scaffold and memory files.

In Progress
Nothing yet.

Blockers
Need user confirmation on:

Whether to port registry.json from v1 or rebuild it

Which pool to use as the first backtest verification target

Whether feeGrowthGlobal fields are available on the subgraph in use
(requires EPIC-4 Step 4.1 audit of fetch_pool_history.py from v1)

Recent Decisions
Clean-room rewrite, not migration. v2 is a new repo.

Seven-layer architecture as documented in systemPatterns.md.

Cline memory pattern in use. Update this file after every session.

Local LLM (Qwen3-27B) via LM Studio. Keep context windows small.
Work one file at a time. Do not load entire v1 codebase into context.

Notes for Next Session
Start with: registry/types.py and registry/registry.py (Layer 1).
These have no dependencies and can be written and tested first.