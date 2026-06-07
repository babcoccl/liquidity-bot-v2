## Current Sprint: 18
**Focus:** Scorer metrics engine — compute real entry metrics from historical PoolHistoryPoint records
**Modified:** backtest/config.py (metrics_window_hours field added, default 720)
**Modified:** core/metrics.py (six new Decimal-only scorer metric functions; AUDIT promoted to complete)
**Modified:** backtest/harness.py (entry gate uses compute_entry_metrics instead of static zeros; AUDIT sprint=18)
**New:** tests/test_metrics.py (24 unit tests for all six new functions)
**Status:** Complete
**Next:** Sprint 19 — backtest.multipool float migration (last partial module); then entry-side integration tests