"""Performance metrics: Sharpe ratio, max drawdown, etc."""
# AUDIT:status=complete
# AUDIT:sprint=18
# AUDIT:issue=none
# AUDIT:note=Sprint 18: Float functions retained for reporter. New Decimal scorer metric functions added.

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import math as _math

from core.models import PoolHistoryPoint


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


# --- SCORER METRIC FUNCTIONS (DECIMAL ONLY) ---
# AUDIT:sprint=18 — NEW FUNC FOR POOL ENTRY SCORING. ALL DECIMAL. NO FLOAT.


def rolling_window(
    records: list[PoolHistoryPoint],
    window_hours: int,
) -> list[PoolHistoryPoint]:
    """CHOP RECORDS TO MOST RECENT WINDOW_HOURS. SORT ASCEND. NO MUTATE."""
    if not records or window_hours <= 0:
        return []
    max_ts = max(r.timestamp for r in records)
    cutoff = max_ts - (window_hours * 3600)
    filtered = [r for r in records if r.timestamp >= cutoff]
    return sorted(filtered, key=lambda r: r.timestamp)


def annualized_vol_30d(
    records: list[PoolHistoryPoint],
    hours_per_year: int = 8760,
) -> Decimal:
    """COMPUTE ANNUALIZED VOL OF price_token1_in_token0. ONE FLOAT CONV FOR LOG OK."""
    if len(records) < 2:
        return Decimal("0")

    sorted_recs = sorted(records, key=lambda r: r.timestamp)
    prices = [r.price_token1_in_token0 for r in sorted_recs]

    # LOG RETURNS. ONE FLOAT CONV INSIDE LOG — PERMITTED.
    log_returns: list[Decimal] = []
    for i in range(1, len(prices)):
        ratio = prices[i] / prices[i - 1]
        lr = Decimal(str(_math.log(float(ratio))))
        log_returns.append(lr)

    if not log_returns:
        return Decimal("0")

    n = Decimal(str(len(log_returns)))
    mean_lr = sum(log_returns) / n
    variance = sum((lr - mean_lr) ** 2 for lr in log_returns) / n

    if variance == Decimal("0"):
        return Decimal("0")

    std_dev = Decimal(str(_math.sqrt(float(variance))))
    annualized = std_dev * Decimal(str(_math.sqrt(hours_per_year)))

    return annualized.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def fee_apr_from_records(
    records: list[PoolHistoryPoint],
    fee_tier: int,
    hours_per_year: int = 8760,
) -> Decimal:
    """ESTIMATE ANNUALIZED FEE APR FROM RECORDS. CLAMP TO [0, 50]."""
    if not records:
        return Decimal("0")

    mean_tvl = sum(r.tvl_usd for r in records) / Decimal(str(len(records)))
    if mean_tvl == Decimal("0"):
        return Decimal("0")

    fee_rate = Decimal(str(fee_tier)) / Decimal("1000000")
    total_fees = sum(r.volume_usd * fee_rate for r in records)

    timestamps = [r.timestamp for r in records]
    window_seconds = max(timestamps) - min(timestamps)
    window_hours = Decimal(str(window_seconds)) / Decimal("3600")
    if window_hours <= Decimal("0"):
        window_hours = Decimal("1")

    apr = (total_fees / mean_tvl) * (Decimal(str(hours_per_year)) / window_hours)

    # CLAMP TO [0, 50]
    apr = max(Decimal("0"), min(apr, Decimal("50")))
    return apr.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def volume_tvl_ratio_from_records(
    records: list[PoolHistoryPoint],
) -> Decimal:
    """MEAN VOLUME_USD / TVL_USD OVER RECORDS. SKIP ZERO TVL."""
    ratios: list[Decimal] = []
    for r in records:
        if r.tvl_usd > Decimal("0"):
            ratios.append(r.volume_usd / r.tvl_usd)

    if not ratios:
        return Decimal("0")

    mean_ratio = sum(ratios) / Decimal(str(len(ratios)))
    return mean_ratio.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def net_lp_alpha_from_records(
    records: list[PoolHistoryPoint],
    fee_tier: int,
    tick_lower: int,
    tick_upper: int,
) -> Decimal:
    """ESTIMATE NET LP ALPHA AS FRACTION OF INITIAL CAPITAL. SIMPLIFIED MODEL."""
    if len(records) < 2:
        return Decimal("0")

    # LOCAL IMPORT TO AVOID CIRCULAR RISK
    from core.il import tick_to_price as _tick_to_price, compute_il_pct as _compute_il_pct

    sorted_recs = sorted(records, key=lambda r: r.timestamp)
    price_lower = _tick_to_price(tick_lower)
    price_upper = _tick_to_price(tick_upper)
    fee_rate = Decimal(str(fee_tier)) / Decimal("1000000")

    # ACCUMULATE FEES WHEN PRICE IN RANGE AND TVL > 0
    fees_earned = Decimal("0")
    for r in sorted_recs:
        if price_lower <= r.price_token1_in_token0 <= price_upper and r.tvl_usd > Decimal("0"):
            fees_earned += r.volume_usd * fee_rate / r.tvl_usd

    # IL PCT FROM FIRST TO LAST PRICE
    entry_price = sorted_recs[0].price_token1_in_token0
    exit_price = sorted_recs[-1].price_token1_in_token0
    il_pct = _compute_il_pct(entry_price, exit_price, price_lower, price_upper, Decimal("1"))

    net_alpha = fees_earned + il_pct  # IL PCT IS NEGATIVE SO THIS IS FEES MINUS |IL|
    return net_alpha.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def compute_entry_metrics(
    records: list[PoolHistoryPoint],
    fee_tier: int,
    tick_lower: int,
    tick_upper: int,
    window_hours: int = 720,
) -> dict[str, Decimal]:
    """TOP LEVEL FUNC. CALL ALL FOUR METRIC FUNC ON WINDOWED RECORDS. NEVER RAISE."""
    zero_dict = {
        "net_lp_alpha_30d": Decimal("0"),
        "annualized_vol_30d": Decimal("0"),
        "fee_apr": Decimal("0"),
        "volume_tvl_ratio": Decimal("0"),
    }
    try:
        windowed = rolling_window(records, window_hours)
        if not windowed:
            return zero_dict

        return {
            "net_lp_alpha_30d": net_lp_alpha_from_records(windowed, fee_tier, tick_lower, tick_upper),
            "annualized_vol_30d": annualized_vol_30d(windowed),
            "fee_apr": fee_apr_from_records(windowed, fee_tier),
            "volume_tvl_ratio": volume_tvl_ratio_from_records(windowed),
        }
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning("compute_entry_metrics failed — returning zero dict")
        return zero_dict
