Active Context
Current Focus
Sprint 2: Data layer / fetcher implementation.

Immediate Task
Implement data/fetcher/ with The Graph API integration for Aerodrome pool data.

In Progress
- Sprint 1 COMPLETE: Full scaffold, all stubs, config, tests passing (91 tests, 81% coverage)

Blockers
None. Scaffold is green. Ready for Sprint 2.

Recent Decisions
- Clean-room rewrite, not migration. v2 is a new repo.
- Seven-layer architecture as documented in systemPatterns.md.
- Cline memory pattern in use. Update this file after every session.
- Local LLM (Qwen3-27B) via LM Studio. Keep context windows small.
- Work one file at a time. Do not load entire v1 codebase into context.

Notes for Next Session
Start with: data/fetcher/graph_client.py - The Graph API client for pool metrics.
Then: data/loader/ - CSV/Parquet ingestion from historical snapshots.