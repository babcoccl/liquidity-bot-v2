## Current Sprint: 17
**Focus:** Entry scoring layer hardening — Decimal migration + config-driven thresholds
**Modified:** strategy/scorer.py, strategy/signals.py, strategy/regime.py (float → Decimal, complete)
**Modified:** config/default.yaml (regime: section added)
**Modified:** backtest/harness.py (entry score gate in _simulate_pool_hourly)
**New:** tests/test_scorer.py, tests/test_signals.py, tests/test_regime.py
**Status:** Complete
**Next:** Sprint 18 — core.metrics + backtest.multipool hardening (last two partial modules); then entry-side integration tests