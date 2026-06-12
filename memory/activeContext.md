# Active Context — Sprint 35
_Archived: memory/archive/sprint_33_pre_closeout.md_
## Current State
- Sprint 34-loader COMPLETE: price_loader.py + test_price_loader.py (14/14 tests, 87/87 tokens loaded)
- Sprint 35 COMPLETE: price_features.py + test_price_features.py delivered
- data/features/price_features.py: compute_features() — returns_1h, returns_24h, vol_24h, vol_168h, momentum_24h, momentum_168h, vol_momentum_24h
- Registry: 434 active Slipstream CL pools, all slot0() verified
- DataFrame loader and feature computation layer ready for strategy integration
## Next Action
- Sprint 36: Wire compute_features() into strategy/scorer.py and strategy/signals.py
- Sprint 36: Replace manual JSON parsing in backtest pipeline with price_loader + compute_features
## Key Files
- registry/registry.json — 434 CL pool entries
- data/loader/price_loader.py — analysis-layer DataFrame loader (Sprint 34-loader)
- data/features/price_features.py — token-level feature computation (Sprint 35)
- tests/test_price_features.py — 16 tests (Sprint 35)
- strategy/scorer.py — pool ranking (Sprint 17, consumes compute_entry_metrics)
- strategy/signals.py — exit signal generation (Sprint 17)
- scripts/fetch_aerodrome_pools.py — pool fetcher (CL type > 0)