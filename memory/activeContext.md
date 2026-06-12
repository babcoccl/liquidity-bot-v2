# Active Context — Sprint 38
_Script: scripts/run_backtest.py_

## Current State
- Sprint 37 COMPLETE: scripts/run_pool_scan.py delivered
- Sprint 38 IN PROGRESS: scripts/run_backtest.py written (orchestration-only backtest runner)
- Script delegates all simulation logic to existing BacktestHarness.run()
- All interfaces confirmed: BacktestConfig.from_yaml(), PoolRegistry, BacktestHarness, BacktestReporter

## Key Files (Sprint 38)
- scripts/run_backtest.py — new orchestration script (this sprint)
- backtest/config.py — BacktestConfig.from_yaml() (no changes)
- backtest/harness.py — BacktestHarness(config, registry).run(run_id) (no changes)
- backtest/reporter.py — BacktestReporter.save(), print_summary() (no changes)
- reporting/run_index.py — RunIndex.append() (no changes)
- registry/registry.py — PoolRegistry.load(), validate(), all() (no changes)

## Next Action
- [YOU RUN] smoke test: `python scripts/run_backtest.py --run-id sprint38_smoke`
- Verify results/runs/sprint38_smoke/summary.json exists and contains required keys
- Commit with memory file updates