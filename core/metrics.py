"""Performance metrics: Sharpe ratio, max drawdown, etc."""
# AUDIT NOTE: All financial parameters use float instead of Decimal (returns, equity_curve, total_value, initial_capital). portfolio_summary returns raw dict. No PoolDayData usage. No hardcoded addresses or config values. Duplicate function name: calculate_max_drawdown and max_drawdown both exist.

from __future__ import annotations


def calculate_sharpe_ratio(returns: list[float], risk_free_rate: float = 0.0) -> float:
    """Compute annualized Sharpe ratio from a list of periodic returns.

    Args:
        returns:         List of decimal returns (e.g., [0.01, -0.005]).
        risk_free_rate:  Annualized risk-free rate (default 0 for crypto).
    """
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = variance ** 0.5

    if std_dev == 0:
        return 0.0

    # Annualize assuming daily returns
    annualized_return = mean_ret * 252
    annualized_vol = std_dev * (252 ** 0.5)

    return (annualized_return - risk_free_rate) / annualized_vol


def calculate_max_drawdown(equity_curve: list[float]) -> float:
    """Compute maximum drawdown from an equity curve.

    Returns a value in (0, 1] where 1 = total loss.
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak if peak > 0 else 0.0
        if drawdown > max_dd:
            max_dd = drawdown

    return max_dd


def calculate_sortino_ratio(returns: list[float]) -> float:
    """Sortino ratio — like Sharpe but penalizes only downside volatility."""
    if len(returns) < 2:
        return 0.0

    mean_ret = sum(returns) / len(returns)
    downside_returns = [min(r, 0) for r in returns]
    downside_var = sum(r ** 2 for r in downside_returns) / (len(returns) - 1)
    downside_std = downside_var ** 0.5

    if downside_std == 0:
        return 0.0

    annualized_return = mean_ret * 252
    annualized_downside = downside_std * (252 ** 0.5)

    return annualized_return / annualized_downside


def calmar_ratio(sharpe: float, max_drawdown: float) -> float:
    """Calmar ratio = annualized return / max drawdown."""
    if max_drawdown <= 0:
        return 0.0
    return sharpe * max_drawdown


def win_rate(returns: list[float]) -> float:
    """Fraction of periods with positive returns."""
    if not returns:
        return 0.0
    wins = sum(1 for r in returns if r > 0)
    return wins / len(returns)


def profit_factor(gains: list[float], losses: list[float]) -> float:
    """Ratio of total gains to total absolute losses."""
    total_losses = sum(abs(l) for l in losses)
    if total_losses == 0:
        return float("inf")
    return sum(gains) / total_losses


def max_drawdown(equity_curve: list[float]) -> float:
    """Alias for calculate_max_drawdown."""
    return calculate_max_drawdown(equity_curve)


def portfolio_summary(
    total_value: float,
    initial_capital: float,
    total_fees_earned: float = 0.0,
    total_il_loss: float = 0.0,
    equity_curve: list[float] | None = None,
) -> dict:
    """Generate a portfolio summary dict compatible with reporting.run_report."""
    pnl = total_value - initial_capital
    pnl_pct = (pnl / initial_capital * 100) if initial_capital > 0 else 0.0
    dd = max_drawdown(equity_curve or [initial_capital, total_value])

    return {
        "initial_capital": initial_capital,
        "final_value": round(total_value, 2),
        "total_pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "max_drawdown": round(dd, 4),
        "total_fees_earned": round(total_fees_earned, 4),
        "total_il_loss": round(total_il_loss, 4),
        "active_positions_at_end": 0,
    }
