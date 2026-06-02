# liquidity-bot-v2

Concentrated liquidity management bot for Aerodrome (Base L2). Backtesting-first architecture with multi-pool portfolio optimization.

## Quick Start

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run smoke tests
pytest tests/ --cov=. --cov-report=term-missing

# Run backtest (Sprint 3+)
python -m backtest.multipool --days 90
```

## Project Structure

| Directory | Purpose |
|-----------|---------|
| `config/` | YAML configuration (all tunable parameters) |
| `data/` | Fetchers, loaders, historical data cache |
| `core/` | IL math, fee tracking, metrics computation |
| `strategy/` | Scoring engine, signal detection, regime classification |
| `backtest/` | Event-driven simulator, multi-pool portfolio logic |
| `execution/` | On-chain executor stubs (NotImplementedError) |
| `reporting/` | Run report generation |
| `registry/` | Pool registry JSON |
| `results/` | Backtest output artifacts |
| `logs/` | Runtime logs |
| `tests/` | pytest suite with coverage gates |
| `memory/` | Agent memory files (progress, context, brief) |

## Configuration

All parameters live in `config/default.yaml`. Never hardcode thresholds in source — always load from config.

## License

MIT