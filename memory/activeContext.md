# Active Context

**Current focus:** Sprint 7 — PositionSimulator Implementation

**In-progress:** none

**Blockers:** none

**Last completed:** Sprint 6 — Registry Population + Backtest Harness (backtest/harness.py, backtest/config.py, backtest/reporter.py, scripts/backtest.py, registry/registry.json populated with 15 pools)

**Note:** PositionSimulator.step() still raises NotImplementedError. BacktestHarness is wired and returns zero-results per pool until Sprint 7 implements step(). Running scripts/backtest.py now will produce a valid zero-result run report — useful for confirming the harness wiring is correct before step() is live.

**Note:** LRDS/WETH excluded from registry — token0 address in v1 registry appears malformed. Verify before adding.