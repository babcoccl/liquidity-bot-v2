"""
pool_feature_bridge.py — Bridge between token-level price features and
pool-level scorer metrics into a single scorer-ready dict.

Consumes:
  - registry.types.PoolConfig (pool metadata: fee_tier, ticks, token symbols)
  - dict[str, pd.DataFrame] from data.loader.price_loader.load_all()
  - list[PoolHistoryPoint] from data.loader.pool_loader.load_pool_history()

Produces:
  - dict[str, Decimal | str] ready for strategy.scorer.rank_pools()

Output contract (build_pool_metrics return value):
  {
    "pool_id"          : str     — pool_cfg.pool_address (lowercase)
    "pair_name"        : str     — pool_cfg.pair_name
    "net_lp_alpha_30d" : Decimal — from compute_entry_metrics()
    "annualized_vol_30d": Decimal — from compute_entry_metrics() (pool-level)
    "fee_apr"          : Decimal — from compute_entry_metrics()
    "volume_tvl_ratio" : Decimal — from compute_entry_metrics()
    "vol_24h"          : Decimal — latest non-NaN vol_24h from compute_features()
    "momentum_24h"     : Decimal — latest non-NaN momentum_24h from compute_features()
    "momentum_168h"    : Decimal — latest non-NaN momentum_168h from compute_features()
    "vol_momentum_24h" : Decimal — latest non-NaN vol_momentum_24h from compute_features()
    "price_features_ok": bool    — True if token price data was found and non-empty
    "pool_records_ok"  : bool    — True if pool history records were non-empty
  }

Token selection logic:
  The bridge resolves which token's price DataFrame to use for price features.
  It tries pool_cfg.token0.symbol first, then pool_cfg.token1.symbol.
  The first symbol found in price_dfs is used. If neither is found, price
  feature columns default to Decimal("0") and price_features_ok=False.

All values in the output dict that are financial metrics are Decimal.
No float leaks out of this module — Decimal(str(float_val)) at conversion boundary.

# AUDIT:status=complete
# AUDIT:sprint=36
"""

import logging
from decimal import Decimal

import pandas as pd

from core.metrics import compute_entry_metrics
from core.models import PoolHistoryPoint
from data.features.price_features import compute_features
from registry.types import PoolConfig

logger = logging.getLogger(__name__)


def _latest_valid(series: pd.Series) -> Decimal:
    """Return the most recent non-NaN value from a float64 Series as Decimal.

    Scans from the end of the series backward. Returns Decimal("0") if
    no valid value is found. Conversion: Decimal(str(float_val)) — never
    Decimal(float_val) directly.
    """
    for val in reversed(series.values.tolist()):
        if val is not None and val == val:  # NaN check: NaN != NaN
            return Decimal(str(val))
    return Decimal("0")


def build_pool_metrics(
    pool_cfg: PoolConfig,
    price_dfs: dict[str, pd.DataFrame],
    pool_records: list[PoolHistoryPoint],
    window_hours: int = 720,
) -> dict:
    """Assemble a scorer-ready metrics dict for a single pool.

    Args:
        pool_cfg:     PoolConfig from registry — provides fee_tier, ticks, token symbols.
        price_dfs:    Dict of symbol -> DataFrame from load_all(). May be empty.
        pool_records: List of PoolHistoryPoint for this pool from load_pool_history().
                      May be empty.
        window_hours: Lookback window passed to compute_entry_metrics (default 720 = 30d).

    Returns:
        Dict with keys and types described in module docstring. Never raises —
        returns zero-valued Decimals and False flags on all error paths.
    """
    pool_id = pool_cfg.pool_address.lower()
    pair_name = pool_cfg.pair_name
    pool_records_ok = bool(pool_records)

    # Pool-level metrics from compute_entry_metrics (has its own try/except returning zero dict on error)
    entry_metrics = compute_entry_metrics(
        records=pool_records,
        fee_tier=pool_cfg.fee_tier,
        tick_lower=pool_cfg.tick_lower,
        tick_upper=pool_cfg.tick_upper,
        window_hours=window_hours,
    )

    # Resolve which token's price DataFrame to use
    price_df: pd.DataFrame | None = None
    used_symbol: str | None = None

    for symbol in (pool_cfg.token0.symbol, pool_cfg.token1.symbol):
        if symbol in price_dfs and not price_dfs[symbol].empty:
            price_df = price_dfs[symbol]
            used_symbol = symbol
            break

    price_features_ok = price_df is not None

    # Extract latest feature values
    vol_24h = Decimal("0")
    momentum_24h = Decimal("0")
    momentum_168h = Decimal("0")
    vol_momentum_24h = Decimal("0")

    if price_features_ok:
        try:
            features = compute_features(price_df)
            vol_24h          = _latest_valid(features["vol_24h"])
            momentum_24h     = _latest_valid(features["momentum_24h"])
            momentum_168h    = _latest_valid(features["momentum_168h"])
            vol_momentum_24h = _latest_valid(features["vol_momentum_24h"])
            logger.debug(
                "pool_feature_bridge: %s using token %s — vol_24h=%s momentum_24h=%s",
                pair_name, used_symbol, vol_24h, momentum_24h,
            )
        except Exception as exc:
            logger.warning(
                "pool_feature_bridge: compute_features failed for %s (token %s): %s",
                pair_name, used_symbol, exc,
            )
            price_features_ok = False

    return {
        "pool_id":             pool_id,
        "pair_name":           pair_name,
        "net_lp_alpha_30d":    entry_metrics["net_lp_alpha_30d"],
        "annualized_vol_30d":  entry_metrics["annualized_vol_30d"],
        "fee_apr":             entry_metrics["fee_apr"],
        "volume_tvl_ratio":    entry_metrics["volume_tvl_ratio"],
        "vol_24h":             vol_24h,
        "momentum_24h":        momentum_24h,
        "momentum_168h":       momentum_168h,
        "vol_momentum_24h":    vol_momentum_24h,
        "price_features_ok":   price_features_ok,
        "pool_records_ok":     pool_records_ok,
    }


def build_all_pool_metrics(
    pool_configs: list[PoolConfig],
    price_dfs: dict[str, pd.DataFrame],
    pool_records_map: dict[str, list[PoolHistoryPoint]],
    window_hours: int = 720,
) -> list[dict]:
    """Run build_pool_metrics for every pool in pool_configs.

    Args:
        pool_configs:     List of PoolConfig from registry.
        price_dfs:        Dict of symbol -> DataFrame from load_all().
        pool_records_map: Dict of pool_address (lowercase) -> list[PoolHistoryPoint].
                          Pools missing from this dict receive an empty records list.
        window_hours:     Lookback window passed through to build_pool_metrics.

    Returns:
        List of scorer-ready metric dicts, one per pool_config entry.
        Never raises — individual pool errors are caught in build_pool_metrics.
        Logs a summary line at INFO level: "build_all_pool_metrics: N pools processed,
        M with price data, K with pool records."
    """
    results = []
    price_ok_count = 0
    records_ok_count = 0

    for cfg in pool_configs:
        records = pool_records_map.get(cfg.pool_address.lower(), [])
        metrics = build_pool_metrics(cfg, price_dfs, records, window_hours)
        results.append(metrics)
        if metrics["price_features_ok"]:
            price_ok_count += 1
        if metrics["pool_records_ok"]:
            records_ok_count += 1

    logger.info(
        "build_all_pool_metrics: %d pools processed, %d with price data, %d with pool records",
        len(results), price_ok_count, records_ok_count,
    )
    return results