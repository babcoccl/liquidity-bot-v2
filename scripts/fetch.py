"""
CLI entrypoint: fetch historical pool data + token histories and save to disk.

Usage:
    python scripts/fetch.py --pool <address> --days <n> [--output <path>]
    python scripts/fetch.py --all --days <n> [--output-dir <path>]

Reads pool metadata from registry/registry.json.
Fetches via FetchRouter (TheGraph -> CoinGecko -> DeFiLlama fallback chain).
Saves each pool to data/historical/<pair_name>.json.
Additionally fetches token0 and token1 USD price histories from CoinGecko
and saves them to data/token_history/<symbol>.json for trend/exit signals.
Runs post-fetch validation and prints any warnings.
"""

# AUDIT:status=complete
# AUDIT:sprint=9

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

from data.fetcher.coingecko import CoinGeckoFetcher
from data.fetcher.defillama import DeFiLlamaFetcher
from data.fetcher.gecko_terminal import GeckoTerminalFetcher
from data.fetcher.router import FetchRouter
from data.fetcher.the_graph import TheGraphFetcher
from data.fetcher.token_prices import TokenPriceFetcher
from data.fetcher.validate_historical import validate_all
from data.loader.pool_loader import save_pool_history
from data.loader.token_loader import save_token_history
from registry.registry import PoolRegistry

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(
        description="Fetch historical pool data and save to disk."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pool", type=str, help="Fetch a single pool by address")
    group.add_argument("--all", action="store_true", help="Fetch all pools in registry")

    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days of history to fetch (default: 90)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (only valid with --pool)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (only valid with --all)",
    )

    args = parser.parse_args()

    if args.days <= 0:
        print("Error: --days must be a positive integer")
        return 1

    logging.basicConfig(level=logging.INFO)

    # Load config
    config_path = Path("config/default.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    ds = config.get("data_sources", {})

    # Build fetchers
    gt_cfg = ds.get("gecko_terminal", {})
    gecko_fetcher = GeckoTerminalFetcher(
        network=gt_cfg.get("network", "base"),
        timeframe=gt_cfg.get("timeframe", "hour"),
        rate_limit_per_min=gt_cfg.get("rate_limit_per_min", 25),
    )

    tg_cfg = ds.get("the_graph", {})
    graph_api_key = os.environ.get("THEGRAPH_API_KEY", tg_cfg.get("api_key", ""))
    graph_fetcher = TheGraphFetcher(
        url=tg_cfg.get("url", "").replace("{api_key}", graph_api_key),
        api_key=graph_api_key,
        rate_limit_per_min=tg_cfg.get("rate_limit_per_min", 30),
    )

    cg_cfg = ds.get("coingecko", {})
    coingecko_api_key = os.environ.get("COINGECKO_API_KEY", cg_cfg.get("api_key", ""))
    coingecko_fetcher = CoinGeckoFetcher(
        api_key=coingecko_api_key,
        rate_limit_per_min=cg_cfg.get("rate_limit_per_min", 30),
        registry_path=Path("registry/registry.json"),
    )

    dl_cfg = ds.get("defillama", {})
    defillama_fetcher = DeFiLlamaFetcher(
        protocol_slug=dl_cfg.get("protocol_slug", "aerodrome-finance"),
        rate_limit_per_min=dl_cfg.get("rate_limit_per_min", 100),
    )

    router = FetchRouter(fetchers=[gecko_fetcher, graph_fetcher, coingecko_fetcher, defillama_fetcher])

    # Build token price fetcher
    token_fetcher = TokenPriceFetcher(
        api_key=coingecko_api_key,
        rate_limit_per_min=cg_cfg.get("rate_limit_per_min", 30),
        registry_path=Path("registry/registry.json"),
    )

    # Load registry
    registry = PoolRegistry(path=Path("registry/registry.json"))
    registry.load()

    if args.pool:
        return _fetch_single(args, router, registry, token_fetcher)
    else:
        return _fetch_all(args, router, registry, token_fetcher)


def _fetch_single(
    args,
    router: FetchRouter,
    registry: PoolRegistry,
    token_fetcher: TokenPriceFetcher,
) -> int:
    try:
        pool = registry.get(args.pool)
    except KeyError:
        print(f"Error: Pool {args.pool} not found in registry")
        return 1

    output_dir = Path("data/historical")
    output_path = Path(args.output) if args.output else output_dir / f"{pool.pair_name}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        records = router.fetch(pool.pool_address, days=args.days)
    except Exception as e:
        logger.error("Fetch failed for %s: %s", pool.pair_name, e)
        return 1

    errors = validate_all(records)
    for err in errors:
        print(f"WARNING: {err.message}")

    save_pool_history(pool.pool_address, pool.pair_name, records, output_path)
    print(f"Saved {len(records)} records for {pool.pair_name} -> {output_path}")

    # Fetch token histories
    _fetch_tokens_for_pool(pool, args.days, token_fetcher)
    return 0


def _fetch_all(
    args,
    router: FetchRouter,
    registry: PoolRegistry,
    token_fetcher: TokenPriceFetcher,
) -> int:
    output_dir = Path(args.output_dir) if args.output_dir else Path("data/historical")
    output_dir.mkdir(parents=True, exist_ok=True)

    pools = registry.all()
    if not pools:
        print("No pools in registry to fetch.")
        return 0

    for pool in pools:
        try:
            records = router.fetch(pool.pool_address, days=args.days)
        except Exception as e:
            logger.error("Fetch failed for %s (%s), skipping: %s", pool.pair_name, pool.pool_address, e)
            continue

        errors = validate_all(records)
        for err in errors:
            print(f"WARNING: {err.message}")

        output_path = output_dir / f"{pool.pair_name}.json"
        save_pool_history(pool.pool_address, pool.pair_name, records, output_path)
        print(f"Saved {len(records)} records for {pool.pair_name} -> {output_path}")

        # Fetch token histories
        _fetch_tokens_for_pool(pool, args.days, token_fetcher)

    return 0


def _fetch_tokens_for_pool(
    pool,
    days: int,
    token_fetcher: TokenPriceFetcher,
) -> None:
    """Fetch and save USD price history for token0 and token1 of a pool."""
    for token_key in ("token0", "token1"):
        token = getattr(pool, token_key)
        symbol = token.symbol
        address = token.address

        # Build unique filename: use symbol_address_prefix to avoid collisions
        addr_short = address[:8]
        filename = f"{symbol}_{addr_short}.json"

        try:
            records = token_fetcher.fetch_token_history(
                token_symbol=symbol,
                token_address=address,
                days=days,
            )
            output_path = Path("data/token_history") / filename
            save_token_history(address, symbol, records, output_path)
            print(f"Saved {len(records)} token records for {symbol} -> {output_path}")
        except Exception as e:
            logger.warning(
                "Token fetch failed for %s (%s), skipping: %s",
                symbol, address, e,
            )


if __name__ == "__main__":
    sys.exit(main())
