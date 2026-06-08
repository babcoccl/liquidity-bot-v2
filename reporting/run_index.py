"""RUN INDEX. TRACK ALL BACKTEST RUN. APPEND ONE ENTRY PER RUN. ATOMIC WRITE."""
# AUDIT:status=complete
# AUDIT:sprint=20
# AUDIT:issue=none

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from backtest.config import BacktestConfig


@dataclass(frozen=True)
class RunIndexEntry:
    """ONE ROW IN run_index.json. HOLD SUMMARY OF ONE RUN."""
    run_id: str
    timestamp: str
    config_hash: str
    pools_evaluated: int
    pools_simulated: int
    pools_skipped_entry_gate: int
    mean_net_lp_alpha: Decimal
    mean_fee_apr: Decimal
    most_common_exit_reason: str | None
    schema_version: int = 1


class RunIndex:
    """MANAGE run_index.json FILE. LOAD, APPEND, QUERY."""

    INDEX_PATH = Path("results/run_index.json")

    def load(self) -> list[RunIndexEntry]:
        """LOAD ALL ENTRY FROM FILE. EMPTY LIST IF MISSING OR BAD."""
        if not self.INDEX_PATH.exists():
            return []
        try:
            with open(self.INDEX_PATH, "r") as f:
                data = json.load(f)
            entries: list[RunIndexEntry] = []
            for item in data:
                entry = RunIndexEntry(
                    run_id=item["run_id"],
                    timestamp=item["timestamp"],
                    config_hash=item["config_hash"],
                    pools_evaluated=item["pools_evaluated"],
                    pools_simulated=item["pools_simulated"],
                    pools_skipped_entry_gate=item["pools_skipped_entry_gate"],
                    mean_net_lp_alpha=Decimal(str(item["mean_net_lp_alpha"])),
                    mean_fee_apr=Decimal(str(item["mean_fee_apr"])),
                    most_common_exit_reason=item.get("most_common_exit_reason"),
                    schema_version=item.get("schema_version", 1),
                )
                entries.append(entry)
            return entries
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("run_index load fail: %s — return empty list", e)
            return []

    def append(self, entry: RunIndexEntry) -> None:
        """ADD ONE ENTRY. ATOMIC WRITE VIA TMP THEN RENAME."""
        existing = self.load()
        existing.append(entry)

        self.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.INDEX_PATH.with_suffix(".tmp")

        serialized = []
        for e in existing:
            serialized.append({
                "schema_version": e.schema_version,
                "run_id": e.run_id,
                "timestamp": e.timestamp,
                "config_hash": e.config_hash,
                "pools_evaluated": e.pools_evaluated,
                "pools_simulated": e.pools_simulated,
                "pools_skipped_entry_gate": e.pools_skipped_entry_gate,
                "mean_net_lp_alpha": str(e.mean_net_lp_alpha),
                "mean_fee_apr": str(e.mean_fee_apr),
                "most_common_exit_reason": e.most_common_exit_reason,
            })

        with open(tmp_path, "w") as f:
            json.dump(serialized, f, indent=2)

        os.replace(str(tmp_path), str(self.INDEX_PATH))

    def latest(self, n: int = 10) -> list[RunIndexEntry]:
        """GET LAST N ENTRY BY TIMESTAMP. ASCENDING ORDER."""
        all_entries = self.load()
        sorted_entries = sorted(all_entries, key=lambda e: e.timestamp)
        return sorted_entries[-n:] if len(sorted_entries) > n else sorted_entries

    @staticmethod
    def config_hash_from_config(config: "BacktestConfig") -> str:
        """MAKE 6-CHAR HASH FROM CONFIG. SORT KEY FOR STABLE."""
        import hashlib

        d = {
            "days": str(config.days),
            "initial_capital": str(config.initial_capital),
            "bollinger_multiplier": str(config.bollinger_multiplier),
            "rotation_margin": str(config.rotation_margin),
            "min_entry_score": str(config.min_entry_score),
            "rebalance_cooldown_hours": str(config.rebalance_cooldown_hours),
            "max_rebalances_per_pool_per_day": str(config.max_rebalances_per_pool_per_day),
            "historical_dir": str(config.historical_dir),
            "registry_path": str(config.registry_path),
            "prices_dir": str(config.prices_dir),
            "hourly_dir": str(config.hourly_dir),
            "max_il_pct": str(config.max_il_pct),
            "min_tvl_usd": str(config.min_tvl_usd),
            "min_volume_usd": str(config.min_volume_usd),
            "max_hold_hours": str(config.max_hold_hours),
            "metrics_window_hours": str(config.metrics_window_hours),
        }
        raw = json.dumps(d, sort_keys=True)
        h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return h[:6]


def _serialize_decimal(value: Decimal) -> str:
    """TURN DECIMAL TO STRING WITH 8 PLACE. ROUND_HALF_UP."""
    return str(value.quantize(Decimal("0.00000001"), rounding="ROUND_HALF_UP"))