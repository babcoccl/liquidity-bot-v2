"""Scaffold smoke tests — verify every stub module is importable and basic contracts hold."""

from __future__ import annotations

import pathlib

import pytest


# ── Import smoke tests ────────────────────────────────────────────────

def test_import_data_fetcher():
    import data.fetcher  # noqa: F401


def test_import_data_loader():
    import data.loader  # noqa: F401


def test_import_core_il():
    import core.il  # noqa: F401


def test_import_core_fees():
    import core.fees  # noqa: F401


def test_import_core_metrics():
    import core.metrics  # noqa: F401


def test_import_strategy_scorer():
    import strategy.scorer  # noqa: F401


def test_import_strategy_signals():
    import strategy.signals  # noqa: F401


def test_import_strategy_regime():
    import strategy.regime  # noqa: F401


def test_import_backtest_simulator():
    import backtest.simulator  # noqa: F401


def test_import_backtest_multipool():
    import backtest.multipool  # noqa: F401


def test_import_execution_base_executor():
    import execution.base_executor  # noqa: F401


def test_import_reporting_run_report():
    import reporting.run_report  # noqa: F401


# ── Config tests ─────────────────────────────────────────────────────

def test_config_loads(default_config: dict):
    """default.yaml must contain all top-level sections."""
    assert "backtest" in default_config
    assert "signals" in default_config
    assert "scoring" in default_config
    assert "risk_tiers" in default_config
    assert "harvesting" in default_config
    assert "data" in default_config


def test_config_backtest_fields(default_config: dict):
    bt = default_config["backtest"]
    assert "days" in bt
    assert "initial_capital" in bt
    assert "bollinger_multiplier" in bt
    assert "rotation_margin" in bt
    assert "min_entry_score" in bt
    assert "rebalance_cooldown_hours" in bt
    assert "max_rebalances_per_pool_per_day" in bt


def test_config_signals_fields(default_config: dict):
    sig = default_config["signals"]
    assert "drawdown_pct" in sig
    assert "momentum_crash_pct_per_hr" in sig
    assert "tvl_collapse_rate" in sig
    assert "il_fee_ratio_threshold" in sig


def test_config_scoring_weights(default_config: dict):
    weights = default_config["scoring"]["weights"]
    assert "net_lp_alpha_30d" in weights
    assert "annualized_vol_30d" in weights
    assert "fee_apr" in weights
    assert "volume_tvl_ratio" in weights


# ── Executor contract tests ──────────────────────────────────────────

def test_executor_mint_raises():
    from execution.base_executor import BaseExecutor

    ex = BaseExecutor()
    with pytest.raises(NotImplementedError):
        ex.mint_position(None, None, None, None)  # type: ignore[arg-type]


def test_executor_burn_raises():
    from execution.base_executor import BaseExecutor

    ex = BaseExecutor()
    with pytest.raises(NotImplementedError):
        ex.burn_position(None)  # type: ignore[arg-type]


def test_executor_harvest_raises():
    from execution.base_executor import BaseExecutor

    ex = BaseExecutor()
    with pytest.raises(NotImplementedError):
        ex.harvest_fees(None)  # type: ignore[arg-type]


def test_executor_get_state_raises():
    from execution.base_executor import BaseExecutor

    ex = BaseExecutor()
    with pytest.raises(NotImplementedError):
        ex.get_position_state(None)  # type: ignore[arg-type]


# ── Core IL stub tests ───────────────────────────────────────────────

def test_il_compute_il_returns_zero_for_flat_price(sample_price_series: list[float]):
    from core.il import compute_impermanent_loss

    flat = [100.0] * 8
    il = compute_impermanent_loss(flat, -887220, -885120)
    assert abs(il) < 1e-9


def test_il_non_zero_price_change():
    from core.il import compute_impermanent_loss

    upward = [100.0, 110.0]
    il = compute_impermanent_loss(upward, -887220, -885120)
    assert il < 0  # IL should be negative (loss) for price movement


# ── Fees stub tests ──────────────────────────────────────────────────

def test_fees_accumulate_startsWith_zero():
    from core.fees import FeeAccumulator

    acc = FeeAccumulator()
    assert acc.total_earned == 0.0


def test_fees_after_add():
    from core.fees import FeeAccumulator

    acc = FeeAccumulator()
    acc.add(10.5)
    assert acc.total_earned == 10.5
    acc.add(4.5)
    assert acc.total_earned == 15.0


# ── Metrics stub tests ───────────────────────────────────────────────

def test_metrics_calculate_sharpe():
    from core.metrics import calculate_sharpe_ratio

    returns = [0.01, -0.005, 0.02, 0.003, -0.01]
    sr = calculate_sharpe_ratio(returns)
    assert isinstance(sr, float)


def test_metrics_calculate_max_drawdown():
    from core.metrics import calculate_max_drawdown

    equity = [100, 110, 105, 95, 120]
    mdd = calculate_max_drawdown(equity)
    assert 0 < mdd <= 1


# ── Strategy scorer stub tests ───────────────────────────────────────

def test_scorer_score_pool_returns_zero_without_data():
    from strategy.scorer import PoolScorer

    scorer = PoolScorer()
    score = scorer.score({})
    assert score == 0.0


# ── Strategy signals stub tests ──────────────────────────────────────

def test_signals_drawdown_signal_false_for_safe_pool():
    from strategy.signals import DrawdownSignal

    sig = DrawdownSignal(threshold=0.15)
    assert sig.check(current_price=100.0, peak_price=100.0) is False


def test_signals_drawdown_signal_true_for_crashed_pool():
    from strategy.signals import DrawdownSignal

    sig = DrawdownSignal(threshold=0.15)
    assert sig.check(current_price=80.0, peak_price=100.0) is True


# ── Strategy regime stub tests ───────────────────────────────────────

def test_regime_classify_returns_string():
    from strategy.regime import RegimeClassifier

    rc = RegimeClassifier()
    result = rc.classify(volatility=0.3, trend=-0.02)
    assert isinstance(result, str)


# ── Backtest simulator stub tests ────────────────────────────────────

def test_simulator_step_raises():
    from backtest.simulator import PositionSimulator

    sim = PositionSimulator(pool_id="x", tick_lower=0, tick_upper=1000, initial_usd=1000.0)
    with pytest.raises(NotImplementedError):
        sim.step(price=100.0, volume=500.0, fees_earned=1.0, timestamp="2025-01-01")


# ── Backtest multipool stub tests ────────────────────────────────────

def test_multipool_summary_has_required_keys(mock_backtest_summary: dict):
    """Verify the summary schema matches what reporting expects."""
    required = {"initial_capital", "final_value", "total_pnl", "pnl_pct",
                 "max_drawdown", "active_positions_at_end"}
    assert required.issubset(mock_backtest_summary.keys())


# ── Reporting stub tests ─────────────────────────────────────────────

def test_generate_run_report_returns_string(mock_backtest_summary: dict, mock_equity_curve: list[float]):
    from reporting.run_report import generate_run_report

    report = generate_run_report(mock_backtest_summary, mock_equity_curve)
    assert isinstance(report, str)
    assert "LIQUIDITY BOT V2" in report


def test_save_report_creates_file(tmp_path: pathlib.Path, mock_backtest_summary: dict, mock_equity_curve: list[float]):
    from reporting.run_report import generate_run_report, save_report

    report = generate_run_report(mock_backtest_summary, mock_equity_curve)
    out = tmp_path / "report.txt"
    save_report(report, str(out))
    assert out.exists()
    assert "LIQUIDITY BOT V2" in out.read_text()


# ── Registry test ────────────────────────────────────────────────────

def test_registry_is_empty_list():
    raw = pathlib.Path("registry/registry.json").read_text()
    import json
    data = json.loads(raw)
    assert isinstance(data, list)
    assert len(data) == 0


# ── Deep coverage: core.il ────────────────────────────────────────────

def test_il_single_price_returns_zero():
    from core.il import compute_impermanent_loss
    assert compute_impermanent_loss([100.0], 0, 1) == 0.0


def test_il_empty_prices_returns_zero():
    from core.il import compute_impermanent_loss
    assert compute_impermanent_loss([], 0, 1) == 0.0


def test_il_zero_price_returns_zero():
    from core.il import compute_impermanent_loss
    assert compute_impermanent_loss([0.0, 100.0], 0, 1) == 0.0


def test_concentrated_liquidity_il_flat():
    from core.il import concentrated_liquidity_il
    assert concentrated_liquidity_il(100.0, 100.0, 90.0, 110.0) == 1.0


def test_concentrated_liquidity_il_zero_price():
    from core.il import concentrated_liquidity_il
    assert concentrated_liquidity_il(0.0, 100.0, 90.0, 110.0) == 1.0


def test_compute_il_loss_dollar_basic():
    from core.il import compute_il_loss_dollar
    assert compute_il_loss_dollar(1000.0, 1000.0, 100.0) == 0.0


def test_compute_il_from_price_series():
    from core.il import compute_il_from_price_series
    flat = [100.0] * 8
    assert compute_il_from_price_series(flat) == 0.0


def test_estimate_il_at_tick_range():
    from core.il import estimate_il_at_tick_range
    flat = [100.0] * 8
    assert estimate_il_at_tick_range(flat, 90.0, 110.0) == 0.0


def test_il_vs_hodl_pnl_flat():
    from core.il import il_vs_hodl_pnl
    result = il_vs_hodl_pnl([100.0] * 8, 1000.0)
    assert result["il_loss_usd"] == 0.0


def test_il_vs_hodl_pnl_short_series():
    from core.il import il_vs_hodl_pnl
    result = il_vs_hodl_pnl([100.0], 1000.0)
    assert result["il_loss_usd"] == 0.0


# ── Deep coverage: core.fees ─────────────────────────────────────────

def test_fees_add_negative():
    from core.fees import FeeAccumulator
    acc = FeeAccumulator()
    acc.add(-5.0)
    assert acc.total_earned == 0.0


def test_fees_reset():
    from core.fees import FeeAccumulator
    acc = FeeAccumulator()
    acc.add(10.0)
    acc.reset()
    assert acc.total_earned == 0.0


def test_compute_fee_apr_basic():
    from core.fees import compute_fee_apr
    apr = compute_fee_apr(100.0, 10000.0, 365)
    assert abs(apr - 0.01) < 1e-9


def test_compute_fee_apr_zero_deposit():
    from core.fees import compute_fee_apr
    assert compute_fee_apr(100.0, 0, 365) == 0.0


def test_estimate_hourly_fees_basic():
    from core.fees import estimate_hourly_fees
    h = estimate_hourly_fees(1_000_000, 100_000, 50)
    assert h > 0


def test_estimate_hourly_fees_zero_tvl():
    from core.fees import estimate_hourly_fees
    assert estimate_hourly_fees(0, 100_000, 50) == 0.0


def test_lp_fee_share_basic():
    from core.fees import lp_fee_share
    share = lp_fee_share(100_000, 1_000_000, 500.0)
    assert abs(share - 50.0) < 1e-9


def test_lp_fee_share_zero_tvl():
    from core.fees import lp_fee_share
    assert lp_fee_share(100_000, 0, 500.0) == 0.0


def test_fee_gas_ratio_basic():
    from core.fees import fee_gas_ratio
    ratio = fee_gas_ratio(30.0, 10.0)
    assert abs(ratio - 3.0) < 1e-9


def test_fee_gas_ratio_zero_gas():
    from core.fees import fee_gas_ratio
    import math
    assert math.isinf(fee_gas_ratio(30.0, 0))


# ── Deep coverage: core.metrics ──────────────────────────────────────

def test_calculate_sharpe_empty():
    from core.metrics import calculate_sharpe_ratio
    assert calculate_sharpe_ratio([]) == 0.0


def test_calculate_sharpe_zero_vol():
    from core.metrics import calculate_sharpe_ratio
    assert calculate_sharpe_ratio([0.0, 0.0, 0.0]) == 0.0


def test_calculate_max_drawdown_empty():
    from core.metrics import calculate_max_drawdown
    assert calculate_max_drawdown([]) == 0.0


def test_calculate_max_drawdown_single():
    from core.metrics import calculate_max_drawdown
    assert calculate_max_drawdown([100.0]) == 0.0


def test_calculate_max_drawdown_no_drop():
    from core.metrics import calculate_max_drawdown
    mdd = calculate_max_drawdown([100, 110, 120])
    assert mdd == 0.0


def test_calculate_sortino_ratio_basic():
    from core.metrics import calculate_sortino_ratio
    sr = calculate_sortino_ratio([0.01, -0.005, 0.02])
    assert isinstance(sr, float)


def test_calculate_sortino_ratio_short():
    from core.metrics import calculate_sortino_ratio
    assert calculate_sortino_ratio([]) == 0.0


def test_calmar_ratio_basic():
    from core.metrics import calmar_ratio
    r = calmar_ratio(1.5, 0.1)
    assert isinstance(r, float)


def test_calmar_ratio_zero_dd():
    from core.metrics import calmar_ratio
    assert calmar_ratio(1.5, 0) == 0.0


def test_win_rate_basic():
    from core.metrics import win_rate
    wr = win_rate([0.01, -0.02, 0.03])
    assert abs(wr - 2/3) < 1e-9


def test_win_rate_empty():
    from core.metrics import win_rate
    assert win_rate([]) == 0.0


def test_profit_factor_basic():
    from core.metrics import profit_factor
    pf = profit_factor([10.0], [-5.0])
    assert abs(pf - 2.0) < 1e-9


def test_profit_factor_no_losses():
    from core.metrics import profit_factor
    import math
    assert math.isinf(profit_factor([10.0], []))


def test_max_drawdown_alias():
    from core.metrics import max_drawdown, calculate_max_drawdown
    curve = [100, 90, 110]
    assert max_drawdown(curve) == calculate_max_drawdown(curve)


def test_portfolio_summary_basic():
    from core.metrics import portfolio_summary
    s = portfolio_summary(11000.0, 10000.0, equity_curve=[10000, 11000])
    assert s["final_value"] == 11000.0
    assert s["total_pnl"] == 1000.0


# ── Deep coverage: strategy.scorer ───────────────────────────────────

def test_scorer_init_sets_weights():
    from strategy.scorer import PoolScorer
    s = PoolScorer()
    assert hasattr(s, "weights")


def test_scorer_normalize_basic():
    from strategy.scorer import PoolScorer
    s = PoolScorer()
    result = s.normalize(50.0, 0.0, 100.0)
    assert abs(result - 0.5) < 1e-9


def test_scorer_normalize_zero_range():
    from strategy.scorer import PoolScorer
    s = PoolScorer()
    result = s.normalize(50.0, 100.0, 100.0)
    assert abs(result - 0.5) < 1e-9


def test_scorer_score_with_data():
    from strategy.scorer import PoolScorer
    s = PoolScorer()
    score = s.score({
        "net_lp_alpha_30d": 0.1,
        "annualized_vol_30d": 0.5,
        "fee_apr": 0.2,
        "volume_tvl_ratio": 0.3,
    })
    assert isinstance(score, float)


# ── Deep coverage: strategy.signals ──────────────────────────────────

def test_signals_drawdown_equal_prices():
    from strategy.signals import DrawdownSignal
    sig = DrawdownSignal(threshold=0.15)
    assert sig.check(current_price=100.0, peak_price=100.0) is False


def test_momentum_crash_signal_no_history():
    from strategy.signals import MomentumCrashSignal
    sig = MomentumCrashSignal(lookback_hrs=3, threshold=0.03)
    assert sig.check(prices=[], now_ts="2025-01-01") is False


def test_momentum_crash_signal_short_history():
    from strategy.signals import MomentumCrashSignal
    sig = MomentumCrashSignal(lookback_hrs=3, threshold=0.03)
    assert sig.check(prices=[100.0], now_ts="2025-01-01") is False


def test_tvl_collapse_signal_no_history():
    from strategy.signals import TVLCollapseSignal
    sig = TVLCollapseSignal(threshold=-0.3)
    assert sig.check(current_tvl=1_000_000, peak_tvl=1_000_000) is False


def test_il_fee_ratio_signal_below_threshold():
    from strategy.signals import ILFeeRatioSignal
    sig = ILFeeRatioSignal(threshold=8.0)
    assert sig.check(il_loss_pct=0.05, fee_apr=0.1) is False


# ── Deep coverage: strategy.regime ───────────────────────────────────

def test_regime_high_volatility():
    from strategy.regime import RegimeClassifier
    rc = RegimeClassifier()
    result = rc.classify(volatility=0.8, trend=-0.1)
    assert isinstance(result, str)


def test_regime_low_vol_positive_trend():
    from strategy.regime import RegimeClassifier
    rc = RegimeClassifier()
    result = rc.classify(volatility=0.1, trend=0.05)
    assert isinstance(result, str)


# ── Deep coverage: backtest.simulator ────────────────────────────────

def test_position_init():
    from backtest.simulator import Position
    p = Position("pool-x", 100.0, 90.0, 110.0, 1000.0)
    assert p.current_value == 1000.0


def test_position_update():
    from backtest.simulator import Position
    p = Position("pool-x", 100.0, 90.0, 110.0, 1000.0)
    p.update(100.0, 5000.0)
    assert p.current_value >= 1000.0


def test_backtest_simulator_init():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=5000.0)
    assert sim.cash == 5000.0


def test_backtest_simulator_enter_and_exit():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=1000.0)
    sim.enter(100.0, capital=500.0)
    assert sim.position is not None
    proceeds = sim.exit()
    assert proceeds > 0


def test_backtest_simulator_enter_no_cash():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=1000.0)
    sim.cash = 0
    sim.enter(100.0)
    assert sim.position is None


def test_backtest_simulator_exit_no_position():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=1000.0)
    assert sim.exit() == 0.0


def test_backtest_simulator_step_no_position():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=1000.0)
    val = sim.step(100.0, 500.0)
    assert val == 1000.0


def test_backtest_simulator_summary():
    from backtest.simulator import BacktestSimulator
    sim = BacktestSimulator("pool-x", initial_capital=1000.0)
    summary = sim.summary()
    assert "final_value" in summary


# ── Deep coverage: execution.base_executor ───────────────────────────

def test_executor_mint_raises():
    from execution.base_executor import BaseExecutor
    ex = BaseExecutor()
    with pytest.raises(NotImplementedError):
        ex.mint_position("pool", 90, 110, 1000.0)


# ── Deep coverage: reporting.run_report ──────────────────────────────

def test_generate_run_report_keys(mock_backtest_summary: dict, mock_equity_curve: list[float]):
    from reporting.run_report import generate_run_report
    report = generate_run_report(mock_backtest_summary, mock_equity_curve)
    assert "Initial Capital" in report or "LIQUIDITY BOT V2" in report


def test_format_position_line():
    from reporting.run_report import format_position_line
    line = format_position_line("pool-x", 1000.0, 50.0, -2.0)
    assert isinstance(line, str)
    assert "pool-x" in line


# ── Sprint 1: PoolDayData tests ───────────────────────────────────────

def test_pool_day_data_construction():
    from decimal import Decimal
    from core.models import PoolDayData
    d = PoolDayData(
        pool_address="0xabc",
        date=1700000000,
        price_token1_in_token0=Decimal("3200.00"),
        price_token0_in_token1=Decimal("0.0003125"),
        volume_usd=Decimal("500000"),
        tvl_usd=Decimal("2000000"),
        fee_growth_global_0=123456789,
        fee_growth_global_1=None,
        source="the_graph",
    )
    assert d.pool_address == "0xabc"
    assert d.fee_growth_global_1 is None
    assert isinstance(d.volume_usd, Decimal)


def test_pool_day_data_is_frozen():
    from decimal import Decimal
    from core.models import PoolDayData
    d = PoolDayData(
        pool_address="0xabc",
        date=1700000000,
        price_token1_in_token0=Decimal("1"),
        price_token0_in_token1=Decimal("1"),
        volume_usd=Decimal("0"),
        tvl_usd=Decimal("0"),
        fee_growth_global_0=None,
        fee_growth_global_1=None,
        source="coingecko",
    )
    with pytest.raises(Exception):
        d.pool_address = "0xchanged"


def test_abstract_fetcher_cannot_instantiate():
    from data.fetcher.base import AbstractFetcher
    with pytest.raises(TypeError):
        AbstractFetcher()


def test_rate_limit_error_is_exception():
    from data.fetcher.base import RateLimitError, FetchError
    assert issubclass(RateLimitError, Exception)
    assert issubclass(FetchError, Exception)
    assert not issubclass(RateLimitError, FetchError)
