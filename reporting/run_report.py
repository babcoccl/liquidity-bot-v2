"""Run report generator for backtest results."""

from __future__ import annotations


def generate_run_report(
    summary: dict,
    equity_curve: list[float],
    pool_results: list[dict] | None = None,
) -> str:
    """Generate a human-readable text report from backtest results.

    Args:
        summary:      Dict with portfolio-level metrics (from MultiPoolBacktest.summary).
        equity_curve: List of portfolio values over time.
        pool_results: Optional list of per-pool result dicts.

    Returns:
        Formatted multi-line string report.
    """
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("         LIQUIDITY BOT V2 — BACKTEST REPORT")
    lines.append("=" * 60)
    lines.append("")

    # Portfolio summary
    lines.append("PORTFOLIO SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Initial Capital:   ${summary.get('initial_capital', 0):>12,.2f}")
    lines.append(f"  Final Value:       ${summary.get('final_value', 0):>12,.2f}")
    lines.append(f"  Total P&L:         ${summary.get('total_pnl', 0):>12,.2f}")
    lines.append(f"  P&L %:             {summary.get('pnl_pct', 0):>11.2f}%")
    lines.append(f"  Max Drawdown:      {summary.get('max_drawdown', 0):>11.4f}")
    lines.append(f"  Active Positions:  {summary.get('active_positions_at_end', 0):>11d}")
    lines.append("")

    # Equity curve stats
    if equity_curve:
        peak = max(equity_curve)
        trough = min(equity_curve)
        lines.append("EQUITY CURVE STATS")
        lines.append("-" * 40)
        lines.append(f"  Peak Value:      ${peak:>12,.2f}")
        lines.append(f"  Trough Value:    ${trough:>12,.2f}")
        lines.append(f"  Data Points:     {len(equity_curve):>11d}")
        lines.append("")

    # Per-pool breakdown
    if pool_results:
        lines.append("PER-POOL BREAKDOWN")
        lines.append("-" * 40)
        lines.append(f"  {'Pool':<25} {'P&L ($)':>12} {'P&L (%)':>10}")
        lines.append("  " + "-" * 47)

        for pool in pool_results:
            pid = pool.get("pool_id", "unknown")[:24]
            pnl = pool.get("pnl", 0.0)
            pnl_pct = pool.get("pnl_pct", 0.0)
            lines.append(f"  {pid:<25} ${pnl:>11,.2f} {pnl_pct:>9.2f}%")

        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def format_position_line(pool_id: str, value: float, pnl_pct: float, il_loss: float) -> str:
    """Format a single position line for reports.

    Args:
        pool_id:   Pool identifier.
        value:     Current USD value.
        pnl_pct:   P&L percentage.
        il_loss:   Impermanent loss in USD.

    Returns:
        Formatted string line.
    """
    return f"  {pool_id:<25} ${value:>12,.2f}  {pnl_pct:>7.2f}%  IL: ${il_loss:>10,.2f}"


def save_report(report_text: str, path: str = "results/run_report.txt") -> None:
    """Save a report string to a file.

    Args:
        report_text: The formatted report text.
        path:        Output file path.
    """
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(report_text)