"""COMPARATOR. COMPARE TWO RUN SUMMARY. FIND DELTA. DECIMAL ONLY. NO FLOAT."""
# AUDIT:status=complete
# AUDIT:sprint=20
# AUDIT:issue=none

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolResult:
    """ONE POOL IN SUMMARY. ALL MONEY VALUE DECIMAL."""
    pool_address: str
    pair_name: str
    risk_tier: str | None
    entry_score: Decimal
    net_lp_alpha: Decimal
    fee_apr: Decimal
    il_cost: Decimal
    total_fees_earned: Decimal
    hours_simulated: int
    exit_reason: str | None
    final_capital: Decimal


@dataclass(frozen=True)
class AggregateStats:
    """AGGREGATE OF ONE RUN. ALL MONEY VALUE DECIMAL."""
    pools_evaluated: int
    pools_simulated: int
    pools_skipped_entry_gate: int
    mean_net_lp_alpha: Decimal
    median_net_lp_alpha: Decimal
    total_fees_earned: Decimal
    mean_fee_apr: Decimal
    mean_hours_simulated: Decimal
    most_common_exit_reason: str | None
    exit_reason_counts: dict[str, int]


@dataclass(frozen=True)
class RunSummary:
    """FULL SUMMARY OF ONE RUN. LOAD FROM summary.json."""
    schema_version: int
    run_id: str
    timestamp: str
    config_snapshot: dict[str, str]
    aggregate: AggregateStats
    pools: list[PoolResult]


@dataclass(frozen=True)
class PoolDelta:
    """DELTA FOR ONE POOL BETWEEN TWO RUN."""
    pool_address: str
    pair_name: str
    net_lp_alpha_a: Decimal
    net_lp_alpha_b: Decimal
    net_lp_alpha_delta: Decimal
    fee_apr_a: Decimal
    fee_apr_b: Decimal
    fee_apr_delta: Decimal
    il_cost_a: Decimal
    il_cost_b: Decimal
    il_cost_delta: Decimal
    exit_reason_a: str | None
    exit_reason_b: str | None
    status: str


@dataclass(frozen=True)
class RunDelta:
    """DELTA BETWEEN TWO RUN. SHOW TREND."""
    run_id_a: str
    run_id_b: str
    mean_alpha_delta: Decimal
    total_fees_delta: Decimal
    pools_skipped_delta: int
    pool_deltas: list[PoolDelta]


def _safe_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    """CONVERT VALUE TO DECIMAL. IF BAD RETURN DEFAULT AND LOG."""
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        logger.warning("_safe_decimal: bad value %s — use %s", value, default)
        return default


def _safe_str(value, default: str | None = None) -> str | None:
    """CONVERT VALUE TO STR OR DEFAULT."""
    if value is None:
        return default
    return str(value)


def compare_runs(a: RunSummary, b: RunSummary) -> RunDelta:
    """COMPARE TWO RUN. RETURN DELTA. NEVER RAISE."""
    # Build pool map by address
    map_a: dict[str, PoolResult] = {}
    for p in a.pools:
        map_a[p.pool_address] = p

    map_b: dict[str, PoolResult] = {}
    for p in b.pools:
        map_b[p.pool_address] = p

    all_addresses = sorted(set(map_a.keys()) | set(map_b.keys()))

    pool_deltas: list[PoolDelta] = []
    for addr in all_addresses:
        pa = map_a.get(addr)
        pb = map_b.get(addr)

        if pa and not pb:
            # dropped
            alpha_a = _safe_decimal(pa.net_lp_alpha)
            fee_a = _safe_decimal(pa.fee_apr)
            il_a = _safe_decimal(pa.il_cost)
            pool_deltas.append(PoolDelta(
                pool_address=addr,
                pair_name=_safe_str(pa.pair_name, "unknown"),
                net_lp_alpha_a=alpha_a,
                net_lp_alpha_b=Decimal("0"),
                net_lp_alpha_delta=-alpha_a,
                fee_apr_a=fee_a,
                fee_apr_b=Decimal("0"),
                fee_apr_delta=-fee_a,
                il_cost_a=il_a,
                il_cost_b=Decimal("0"),
                il_cost_delta=-il_a,
                exit_reason_a=_safe_str(pa.exit_reason),
                exit_reason_b=None,
                status="dropped",
            ))
        elif pb and not pa:
            # added
            alpha_b = _safe_decimal(pb.net_lp_alpha)
            fee_b = _safe_decimal(pb.fee_apr)
            il_b = _safe_decimal(pb.il_cost)
            pool_deltas.append(PoolDelta(
                pool_address=addr,
                pair_name=_safe_str(pb.pair_name, "unknown"),
                net_lp_alpha_a=Decimal("0"),
                net_lp_alpha_b=alpha_b,
                net_lp_alpha_delta=alpha_b,
                fee_apr_a=Decimal("0"),
                fee_apr_b=fee_b,
                fee_apr_delta=fee_b,
                il_cost_a=Decimal("0"),
                il_cost_b=il_b,
                il_cost_delta=il_b,
                exit_reason_a=None,
                exit_reason_b=_safe_str(pb.exit_reason),
                status="added",
            ))
        else:
            # both exist
            alpha_a = _safe_decimal(pa.net_lp_alpha if pa else None)
            alpha_b = _safe_decimal(pb.net_lp_alpha if pb else None)
            delta = alpha_b - alpha_a

            if delta > Decimal("0.001"):
                status = "improved"
            elif delta < Decimal("-0.001"):
                status = "degraded"
            else:
                status = "unchanged"

            fee_a = _safe_decimal(pa.fee_apr if pa else None)
            fee_b = _safe_decimal(pb.fee_apr if pb else None)
            il_a = _safe_decimal(pa.il_cost if pa else None)
            il_b = _safe_decimal(pb.il_cost if pb else None)

            pair_name = _safe_str(pb.pair_name if pb else pa.pair_name, "unknown")

            pool_deltas.append(PoolDelta(
                pool_address=addr,
                pair_name=pair_name,
                net_lp_alpha_a=alpha_a,
                net_lp_alpha_b=alpha_b,
                net_lp_alpha_delta=delta,
                fee_apr_a=fee_a,
                fee_apr_b=fee_b,
                fee_apr_delta=fee_b - fee_a,
                il_cost_a=il_a,
                il_cost_b=il_b,
                il_cost_delta=il_b - il_a,
                exit_reason_a=_safe_str(pa.exit_reason if pa else None),
                exit_reason_b=_safe_str(pb.exit_reason if pb else None),
                status=status,
            ))

    mean_alpha_delta = b.aggregate.mean_net_lp_alpha - a.aggregate.mean_net_lp_alpha
    total_fees_delta = b.aggregate.total_fees_earned - a.aggregate.total_fees_earned
    pools_skipped_delta = b.aggregate.pools_skipped_entry_gate - a.aggregate.pools_skipped_entry_gate

    return RunDelta(
        run_id_a=a.run_id,
        run_id_b=b.run_id,
        mean_alpha_delta=mean_alpha_delta,
        total_fees_delta=total_fees_delta,
        pools_skipped_delta=pools_skipped_delta,
        pool_deltas=pool_deltas,
    )


def load_run_summary(run_id: str) -> RunSummary:
    """LOAD summary.json FOR ONE RUN. RAISE FileNotFoundError IF MISSING."""
    summary_path = Path("results/runs") / run_id / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(
            f"summary.json not found for run {run_id} at {summary_path}"
        )

    with open(summary_path, "r") as f:
        data = json.load(f)

    agg = data["aggregate"]
    aggregate = AggregateStats(
        pools_evaluated=agg["pools_evaluated"],
        pools_simulated=agg["pools_simulated"],
        pools_skipped_entry_gate=agg["pools_skipped_entry_gate"],
        mean_net_lp_alpha=Decimal(str(agg["mean_net_lp_alpha"])),
        median_net_lp_alpha=Decimal(str(agg["median_net_lp_alpha"])),
        total_fees_earned=Decimal(str(agg["total_fees_earned"])),
        mean_fee_apr=Decimal(str(agg["mean_fee_apr"])),
        mean_hours_simulated=Decimal(str(agg["mean_hours_simulated"])),
        most_common_exit_reason=agg.get("most_common_exit_reason"),
        exit_reason_counts=agg.get("exit_reason_counts", {}),
    )

    pools: list[PoolResult] = []
    for p in data.get("pools", []):
        pools.append(PoolResult(
            pool_address=p["pool_address"],
            pair_name=p["pair_name"],
            risk_tier=p.get("risk_tier"),
            entry_score=Decimal(str(p.get("entry_score", "0"))),
            net_lp_alpha=Decimal(str(p["net_lp_alpha"])),
            fee_apr=Decimal(str(p["fee_apr"])),
            il_cost=Decimal(str(p["il_cost"])),
            total_fees_earned=Decimal(str(p["total_fees_earned"])),
            hours_simulated=p["hours_simulated"],
            exit_reason=p.get("exit_reason"),
            final_capital=Decimal(str(p["final_capital"])),
        ))

    return RunSummary(
        schema_version=data.get("schema_version", 1),
        run_id=data["run_id"],
        timestamp=data["timestamp"],
        config_snapshot=data.get("config_snapshot", {}),
        aggregate=aggregate,
        pools=pools,
    )