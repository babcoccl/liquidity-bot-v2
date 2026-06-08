"""DISPLAY. PRINT REPORT TO STDOUT. NO FILE IO. ONLY ACCEPT LOADED OBJECT."""
# AUDIT:status=complete
# AUDIT:sprint=20
# AUDIT:issue=none

from __future__ import annotations

from decimal import Decimal

from reporting.comparator import PoolDelta, RunDelta, RunSummary
from reporting.run_index import RunIndexEntry


def _fmt_alpha(val: Decimal) -> str:
    """FORMAT ALPHA AS PERCENTAGE WITH SIGN."""
    pct = val * Decimal("100")
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.2f}%"


def _fmt_pct(val: Decimal) -> str:
    """FORMAT VALUE AS PERCENTAGE."""
    pct = val * Decimal("100")
    return f"{pct:.2f}%"


def _fmt_money(val: Decimal) -> str:
    """FORMAT MONEY VALUE WITH DOLLAR SIGN."""
    return f"${val:.2f}"


def print_run_summary(summary: RunSummary) -> None:
    """PRINT FORMATTED REPORT FOR ONE RUN."""
    sep = "=" * 54

    print(sep)
    print(f"RUN: {summary.run_id}  |  {summary.timestamp}")
    print(sep)
    print()

    # CONFIG SECTION
    print("CONFIG")
    config = summary.config_snapshot
    for key in ["days", "min_entry_score", "max_il_pct", "min_tvl_usd",
                "min_volume_usd", "metrics_window_hours", "initial_capital"]:
        val = config.get(key, "-")
        print(f"  {key:<21}: {val}")
    print()

    # AGGREGATE SECTION
    agg = summary.aggregate
    print("AGGREGATE")
    print(f"  Pools evaluated       : {agg.pools_evaluated}")
    print(f"  Pools simulated       : {agg.pools_simulated}")
    print(f"  Skipped (entry gate)  : {agg.pools_skipped_entry_gate}")
    print(f"  Mean net alpha        : {_fmt_alpha(agg.mean_net_lp_alpha)}")
    print(f"  Median net alpha      : {_fmt_alpha(agg.median_net_lp_alpha)}")
    print(f"  Total fees earned     : {_fmt_money(agg.total_fees_earned)}")
    fee_apr_pct = agg.mean_fee_apr * Decimal("100")
    print(f"  Mean fee APR          : {fee_apr_pct:.2f}%")
    print(f"  Mean hours simulated  : {agg.mean_hours_simulated:.0f}")

    # Exit reason breakdown
    if agg.exit_reason_counts:
        parts = "  ".join(
            f"{reason}={count}" for reason, count in sorted(agg.exit_reason_counts.items())
        )
        print(f"  Exit reason breakdown : {parts}")
    else:
        print("  Exit reason breakdown : (none)")
    print()

    # POOL DETAIL SECTION
    print("POOL DETAIL")
    header = f"  {'Pair':<16} {'Tier':<10} {'Score':>6}  {'Alpha':>8}  " \
             f"{'FeeAPR':>8}  {'IL Cost':>8}  {'Hours':>6}  Exit"
    print(header)

    for p in summary.pools:
        tier = (p.risk_tier or "-")[:10]
        score_str = f"{p.entry_score:.2f}" if p.entry_score else "-"
        alpha_str = _fmt_alpha(p.net_lp_alpha)
        fee_str = _fmt_pct(p.fee_apr)
        il_str = _fmt_pct(p.il_cost)
        hours = p.hours_simulated

        # Exit reason display
        if hours == 0 and p.exit_reason and "THRESHOLD" in p.exit_reason:
            exit_display = "SKIPPED"
        elif p.exit_reason:
            exit_display = p.exit_reason
        else:
            exit_display = "-"

        line = f"  {p.pair_name:<16} {tier:<10} {score_str:>6}  {alpha_str:>8}  " \
               f"{fee_str:>8}  {il_str:>8}  {hours:>6}  {exit_display}"
        print(line)


def print_run_comparison(delta: RunDelta) -> None:
    """PRINT SIDE-BY-SIDE COMPARISON OF TWO RUN."""
    print(f"COMPARISON: {delta.run_id_a}  →  {delta.run_id_b}")

    # Mean alpha line
    arrow = "▲" if delta.mean_alpha_delta >= 0 else "▼"
    sign = "+" if delta.mean_alpha_delta >= 0 else ""
    print(
        f"  Mean alpha      : {delta.mean_alpha_delta:.4f}  "
        f"{arrow} {sign}{delta.mean_alpha_delta:.4f}"
    )

    # Total fees line
    fee_arrow = "▲" if delta.total_fees_delta >= 0 else "▼"
    fee_sign = "+" if delta.total_fees_delta >= 0 else ""
    print(
        f"  Total fees      : {_fmt_money(delta.total_fees_delta)}  "
        f"{fee_arrow} {fee_sign}{_fmt_money(delta.total_fees_delta)}"
    )

    # Pools skipped line
    skip_word = "better" if delta.pools_skipped_delta <= 0 else "worse"
    skip_arrow = "▲" if delta.pools_skipped_delta <= 0 else "▼"
    print(
        f"  Pools skipped   : {delta.pools_skipped_delta}  "
        f"{skip_arrow} {skip_word}"
    )

    print()
    print("POOL CHANGES")
    header = f"  {'Pair':<16} {'Status':<10} {'Alpha A':>8}  {'Alpha B':>8}  Δ Alpha"
    print(header)

    for d in delta.pool_deltas:
        alpha_a_str = _fmt_alpha(d.net_lp_alpha_a) if d.status not in ("added",) else "—"
        alpha_b_str = _fmt_alpha(d.net_lp_alpha_b) if d.status not in ("dropped",) else "—"

        if d.status in ("added", "dropped"):
            delta_str = "—"
        else:
            delta_arrow = "▲" if d.net_lp_alpha_delta >= 0 else "▼"
            sign = "+" if d.net_lp_alpha_delta >= 0 else ""
            delta_str = f"{delta_arrow} {sign}{_fmt_alpha(d.net_lp_alpha_delta)}"

        line = f"  {d.pair_name:<16} {d.status:<10} {alpha_a_str:>8}  {alpha_b_str:>8}  {delta_str}"
        print(line)


def print_run_history(entries: list[RunIndexEntry]) -> None:
    """PRINT COMPACT TIMELINE TABLE OF LAST RUN."""
    n = len(entries)
    display_n = min(n, 10)
    print(f"RUN HISTORY (last {display_n})")

    header = f"  {'Run ID':<24} {'Date':<12} {'Alpha':>8}  {'FeeAPR':>7} " \
             f"{'Simulated':>10} {'Skip':>5}  Top Exit"
    print(header)

    for e in entries:
        # Date from timestamp (first 10 chars of ISO string)
        date_str = e.timestamp[:10] if len(e.timestamp) >= 10 else e.timestamp

        alpha_str = _fmt_alpha(e.mean_net_lp_alpha)
        fee_apr_pct = e.mean_fee_apr * Decimal("100")
        fee_str = f"{fee_apr_pct:.1f}%"

        exit_display = e.most_common_exit_reason or "-"

        line = f"  {e.run_id:<24} {date_str:<12} {alpha_str:>8}  {fee_str:>7} " \
               f"{e.pools_simulated:>10} {e.pools_skipped_entry_gate:>5}  {exit_display}"
        print(line)