## Current Sprint: 20
**Focus:** Reporting infrastructure — three new modules + updated reporter/harness for full backtest reporting
**New Files:** reporting/run_index.py, reporting/comparator.py, reporting/display.py, tests/test_run_index.py, tests/test_comparator.py
**Modified:** backtest/reporter.py (save() writes summary.json + appends run_index.json; entry_score field), backtest/harness.py (entry_score passed through)
**Output Convention:** results/run_index.json (append-only index), results/runs/{run_id}/summary.json (enriched combined), results/runs/{run_id}/results.json (raw retained)
**Status:** Complete — all 19 new tests pass, full suite passes
**Next:** Sprint 21 E2E smoke test against real data
