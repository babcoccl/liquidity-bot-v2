# Active Context — Sprint 37
_Archived: memory/archive/sprint_33_pre_closeout.md_
## Current State
- Sprint 34-loader COMPLETE: price_loader.py + test_price_loader.py (14/14 tests)
- Sprint 35 COMPLETE: price_features.py + test_price_features.py (16/16 tests)
- Sprint 36 COMPLETE: pool_feature_bridge.py + test_pool_feature_bridge.py delivered
- Sprint 37 IN PROGRESS: scripts/run_pool_scan.py written, blocked by registry fee_tier data quality
- Registry validation fails: most pools have fee_tier values (50000, 300000) not in validator's allowed set {100, 500, 3000, 10000}
- run_pool_scan.py exits code 1 correctly on dirty registry per spec requirement
## Next Action
- Sprint 37 (cont): Fix registry fee_tier values to match validator's allowed set {100, 500, 3000, 10000}, then re-run pool_scan
- Sprint 38: Wire price_loader + compute_features into backtest/harness.py (replace manual JSON parsing)
## Key Files
- registry/registry.json — 434 CL pool entries
- data/loader/price_loader.py — analysis-layer DataFrame loader (Sprint 34-loader)
- data/features/price_features.py — token-level feature computation (Sprint 35)
- data/features/pool_feature_bridge.py — scorer-ready dict assembly (Sprint 36)
- tests/test_pool_feature_bridge.py — 14 tests (Sprint 36)
- strategy/scorer.py — pool ranking, consumes build_all_pool_metrics() output
- strategy/signals.py — exit signal generation
- scripts/fetch_aerodrome_pools.py — pool fetcher (CL type > 0)