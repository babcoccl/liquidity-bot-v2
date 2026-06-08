"""
GENERATE E2E FIXTURES. SYNTHETIC DATA FOR SPRINT 21 TESTS.
NO NETWORK CALLS. NO PYTEST. IDEMPOTENT.

POOL SELECTION FROM registry/registry.json:
- USDC-WETH (0.05% FEE): 0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59
- WETH-cbBTC (0.05% FEE): 0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1
- USDC-USDT (STABLECOIN): 0xa41bc0affba7fd420d186b84899d7ab2ac57fcd1

TOKENS NEEDED: WETH, USDC, USDT, CBBTC
"""

import json
import math
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent
HOURLY_DIR = FIXTURES_DIR / "hourly_e2e"
PRICES_DIR = FIXTURES_DIR / "prices_e2e"

# -- CONSTANTS --
START_TS = 1700000000
INTERVAL = 3600
NUM_RECORDS = 850  # COVER 800+ AT 24H/DAY = ~35 DAYS

# -- POOL ADDRESSES (FROM registry/registry.json) --
POOLS = [
    {
        "pool_address": "0xb2cc224c1c9fee385f8ad6a55b4d94e92359dc59",
        "pair_name": "USDC-WETH",
        "token0_symbol": "USDC",
        "token1_symbol": "WETH",
        "fee_tier": 500,
        "tick_lower": -887272,
        "tick_upper": 887272,
    },
    {
        "pool_address": "0x70acdf2ad0bf2402c957154f944c19ef4e1cbae1",
        "pair_name": "WETH-cbBTC",
        "token0_symbol": "WETH",
        "token1_symbol": "cbBTC",
        "fee_tier": 500,
        "tick_lower": -2000,
        "tick_upper": 2000,
    },
    {
        "pool_address": "0xa41bc0affba7fd420d186b84899d7ab2ac57fcd1",
        "pair_name": "USDC-USDT",
        "token0_symbol": "USDC",
        "token1_symbol": "USDT",
        "fee_tier": 100,
        "tick_lower": -50,
        "tick_upper": 50,
    },
]


def _weth_price(ts_offset: int) -> float:
    """SYNTHETIC WETH PRICE. OSCILLATE AROUND 2500 WITH SMALL NOISE."""
    base = 2500.0
    cycle = math.sin(ts_offset * 0.01) * 30.0
    trend = (ts_offset / NUM_RECORDS) * 10.0
    return round(base + cycle + trend, 4)


def _cbbtc_price(ts_offset: int) -> float:
    """SYNTHETIC CBBTC PRICE. OSCILLATE AROUND 65000."""
    base = 65000.0
    cycle = math.sin(ts_offset * 0.008 + 1.0) * 500.0
    trend = (ts_offset / NUM_RECORDS) * 200.0
    return round(base + cycle + trend, 4)


def _stable_price(ts_offset: int) -> float:
    """SYNTHETIC STABLECOIN PRICE. NEARLY CONSTANT AT 1.0."""
    return round(1.0 + math.sin(ts_offset * 0.02) * 0.0003, 6)


def generate_registry_fixture():
    """WRITE registry_e2e.json WITH 3 POOL ENTRIES."""
    registry = []
    for pool in POOLS:
        entry = {
            "pool_address": pool["pool_address"],
            "pair_name": pool["pair_name"],
            "token0": {
                "symbol": pool["token0_symbol"],
                "address": "",
                "decimals": 6 if pool["token0_symbol"] in ("USDC", "USDT") else 18,
            },
            "token1": {
                "symbol": pool["token1_symbol"],
                "address": "",
                "decimals": 6 if pool["token1_symbol"] == "USDT" else 18,
            },
            "fee_tier": pool["fee_tier"],
            "tick_lower": pool["tick_lower"],
            "tick_upper": pool["tick_upper"],
        }
        registry.append(entry)

    out = FIXTURES_DIR / "registry_e2e.json"
    with open(out, "w") as f:
        json.dump(registry, f, indent=2)
    print(f"WROTE {out} ({len(registry)} POOLS)")


def generate_hourly_fixtures():
    """WRITE HOURLY POOL HISTORY FILES FOR EACH POOL."""
    HOURLY_DIR.mkdir(parents=True, exist_ok=True)

    for pool in POOLS:
        records = []
        addr = pool["pool_address"]
        pair = pool["pair_name"]

        for i in range(NUM_RECORDS):
            ts = START_TS + i * INTERVAL

            # COMPUTE PRICE TOKEN1 IN TOKEN0
            if "USDC-WETH" in pair:
                # USDC is token0, WETH is token1. price = WETH_USD / USDC_USD ~ 2500
                price = _weth_price(i)
            elif "WETH-cbBTC" in pair:
                # WETH is token0, cbBTC is token1. price = CBBTC_USD / WETH_USD ~ 26
                weth_p = _weth_price(i)
                cbbtc_p = _cbbtc_price(i)
                price = round(cbbtc_p / weth_p, 8)
            elif "USDC-USDT" in pair:
                # STABLECOIN. PRICE ~ 1.0
                price = _stable_price(i)
            else:
                price = 1.0

            # TVL ABOVE MIN_THRESHOLD (100K). OSCILLATE AROUND 500K.
            tvl = round(500000 + math.sin(i * 0.03) * 100000, 2)

            # VOLUME ABOVE MIN_THRESHOLD (10K). OSCILLATE AROUND 80K.
            volume = round(80000 + math.sin(i * 0.05 + 2.0) * 20000, 2)

            # FEE GROWTH: MONOTONIC INCREASING (SIMULATE ACCUMULATED FEES)
            fee_growth = int(1e18 + i * 5e13)

            records.append({
                "timestamp": ts,
                "price_token1_in_token0": str(price),
                "price_token0_in_token1": str(round(1.0 / price, 10) if price > 0 else "0"),
                "volume_usd": str(volume),
                "tvl_usd": str(tvl),
                "fee_growth_global_0": fee_growth,
                "fee_growth_global_1": fee_growth,
                "source": "synthetic_e2e",
            })

        payload = {
            "pool_address": addr.lower(),
            "pair_name": pair,
            "fetched_at": START_TS + NUM_RECORDS * INTERVAL,
            "records": records,
        }

        out = HOURLY_DIR / f"{pair}.json"
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"WROTE {out} ({len(records)} RECORDS)")


def generate_price_fixtures():
    """WRITE TOKEN PRICE FILES FOR WETH, USDC, USDT, CBBTC."""
    PRICES_DIR.mkdir(parents=True, exist_ok=True)

    tokens = [
        {"symbol": "WETH", "address": "0x4200000000000000000000000000000000000006", "base_price": 2500.0},
        {"symbol": "USDC", "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", "base_price": 1.0},
        {"symbol": "USDT", "address": "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2", "base_price": 1.0},
        {"symbol": "CBBTC", "address": "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", "base_price": 65000.0},
    ]

    for token in tokens:
        records = []
        symbol = token["symbol"]
        base = token["base_price"]

        for i in range(NUM_RECORDS):
            ts = START_TS + i * INTERVAL

            if symbol == "WETH":
                price = _weth_price(i)
            elif symbol == "CBBTC":
                price = _cbbtc_price(i)
            else:
                # STABLECOIN
                price = round(1.0 + math.sin(i * 0.02 + hash(symbol) % 100) * 0.0005, 6)

            volume = round(100000000 + math.sin(i * 0.04) * 20000000, 2)
            mcap = round(base * 10000000, 2)  # SYNTHETIC MARKET CAP

            records.append({
                "timestamp": ts,
                "price_usd": str(price),
                "volume_usd": str(volume),
                "market_cap_usd": str(mcap),
                "source": "synthetic_e2e",
            })

        payload = {
            "token_address": token["address"].lower(),
            "symbol": symbol,
            "fetched_at": START_TS + NUM_RECORDS * INTERVAL,
            "records": records,
        }

        out = PRICES_DIR / f"{symbol}.json"
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"WROTE {out} ({len(records)} RECORDS)")


if __name__ == "__main__":
    print("=== GENERATE E2E FIXTURES ===")
    generate_registry_fixture()
    generate_hourly_fixtures()
    generate_price_fixtures()
    print("=== DONE ===")