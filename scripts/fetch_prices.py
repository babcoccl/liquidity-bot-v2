#!/usr/bin/env python3
"""
Sprint 34: On-chain price feed via Multicall3 slot0().

Reads registry/registry.json, calls slot0() on every pool via a single
Multicall3 aggregate3 call, decodes sqrtPriceX96 to human-readable USD
prices, writes results to data/prices/prices_latest.json.

Usage:
    python scripts/fetch_prices.py

Env vars (loaded from .env):
    BASE_RPC_HTTP   — Base L2 HTTP RPC endpoint (required)
"""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
SLOT0_SELECTOR = "0x3850c7bd"          # slot0()
REGISTRY_PATH = Path("registry/registry.json")
OUTPUT_PATH = Path("data/prices/prices_latest.json")

# CoinGecko token ID mapping (symbol -> coingecko_id)
_COINGECKO_IDS: dict[str, str] = {
    "WETH": "weth",
    "USDC": "usd-coin",
    "USDT": "tether",
    "cbBTC": "coinbase-wrapped-btc",
    "AERO": "aerodrome-finance",
    "VVV": "velodrome-finance-v2",
    "DAI": "dai",
    "WBTC": "wrapped-bitcoin",
    "USDe": "ethereum-defi-index",
    "sDAI": "sdai",
    "rETH": "rocket-pool-eth",
    "wstETH": "lido-wrapped-staked-ether",
    "LDO": "lido-dao",
    "PENDLE": "pendle",
    "MIM": "magic-internet-money",
    "FRAX": "frax",
    "FXS": "frax-share",
    "CRV": "curve-dao-token",
    "UNI": "uniswap",
}

# Known stablecoin symbols — price ~1.0 USD by definition.
_STABLECOINS = {"USDC", "USDT", "DAI", "FRAX", "MIM", "USDe"}


# ─────────────────────────────────────────────
# ABI HELPERS (pure Python, no web3 dependency)
# ─────────────────────────────────────────────

def _pad32(value_hex: str) -> str:
    """Right-pad a hex string (no 0x prefix) to 64 hex chars (32 bytes)."""
    return value_hex.zfill(64)


def _bytes_length_prefix(data_hex: str) -> str:
    """ABI-encode a dynamic bytes value: length (32 bytes) + data padded to 32-byte boundary."""
    parts = [f"{len(data_hex)//2:064x}", data_hex]
    total_len = 64 + len(data_hex)
    remainder = total_len % 64
    if remainder:
        parts.append("0" * (64 - remainder))
    return "".join(parts)


def decode_slot0(return_data: str) -> tuple[int, int]:
    """Decode slot0() return data.

    slot0 returns:
        (uint160 sqrtPriceX96, int24 tick, uint16 observationIndex, ...)

    We only need sqrtPriceX96 and tick.
    """
    raw = return_data.removeprefix("0x")
    if len(raw) < 128:
        raise ValueError(f"slot0 return data too short: {len(raw)} hex chars")

    # sqrtPriceX96 is uint160 -> first 32 bytes (64 hex chars)
    sqrt_price_x96 = int(raw[:64], 16)

    # tick is int24 -> next 32 bytes, sign-extended to 256 bits
    tick_raw = int(raw[64:128], 16)
    if tick_raw >= 2**23:
        tick = tick_raw - 2**24
    else:
        tick = tick_raw

    return sqrt_price_x96, tick


def compute_price(sqrt_price_x96: int, decimals0: int, decimals1: int) -> Decimal:
    """Compute token1/token0 price ratio from sqrtPriceX96.

    price_token1_per_token0 = (sqrtPriceX96 / 2^96)^2
    Adjusted for decimal differences between tokens.

    Returns Decimal ratio of token1 per token0 (in display units).
    """
    Q96 = Decimal(2**96)
    sqrt_ratio = Decimal(sqrt_price_x96) / Q96
    price_ratio = sqrt_ratio * sqrt_ratio

    # Adjust for decimal differences
    dec_adjustment = Decimal(10) ** Decimal(decimals0 - decimals1)
    return price_ratio * dec_adjustment


def build_aggregate3_calldata(targets: list[str], call_datas: list[str]) -> str:
    """Build Multicall3 aggregate3 calldata.

    aggregate3(Call[] calls) returns (Result[] returnData)
    where Call = {target: address, allowFailure: bool, callData: bytes}

    ABI encoding of (address,bool,bytes)[].
    """
    n = len(targets)
    func_sel = "b824b87c"

    tuple_size = 3 * 32  # 96 bytes per tuple header

    tuples_start = 64  # byte offset where tuple headers begin
    blobs_start = tuples_start + n * tuple_size  # byte offset where data blobs begin

    hex_parts: list[str] = []

    # Header: offset to array (32) + array length (n)
    hex_parts.append(f"{32:064x}")
    hex_parts.append(f"{n:064x}")

    current_blob_offset = blobs_start

    for i in range(n):
        addr_hex = targets[i].lower().removeprefix("0x")
        hex_parts.append(_pad32(addr_hex))

        # allowFailure = false
        hex_parts.append("0" * 64)

        # Offset to this callData blob (in bytes from calldata start)
        hex_parts.append(f"{current_blob_offset:064x}")

        # Calculate next blob offset
        cd_raw = call_datas[i].removeprefix("0x")
        total_data_hex = 64 + len(cd_raw)
        remainder = total_data_hex % 64
        if remainder:
            total_data_hex += 64 - remainder
        blob_bytes = total_data_hex // 2
        current_blob_offset += blob_bytes

    # Append callData blobs (ABI-encoded bytes)
    for cd in call_datas:
        raw = cd.removeprefix("0x")
        hex_parts.append(_bytes_length_prefix(raw))

    return "0x" + func_sel + "".join(hex_parts)


# ─────────────────────────────────────────────
# RPC HELPERS (urllib only)
# ─────────────────────────────────────────────

def rpc_call(method: str, params: list, rpc_url: str) -> dict:
    """Send a JSON-RPC call via urllib. Returns the result dict."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }).encode("utf-8")

    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"RPC HTTP {e.code}: {error_body[:300]}")
        sys.exit(1)
    except Exception as e:
        print(f"RPC call failed: {e}")
        sys.exit(1)

    if "error" in body:
        print(f"RPC error: {body['error']}")
        sys.exit(1)

    return body["result"]


# ─────────────────────────────────────────────
# COINGECKO SPOT PRICE (urllib)
# ─────────────────────────────────────────────

def fetch_coingecko_spot_prices(symbol_ids: dict[str, str]) -> dict[str, Decimal]:
    """Fetch current USD prices via CoinGecko /simple/price endpoint.

    Returns {symbol: Decimal(price_usd)} for successfully fetched tokens.
    """
    import urllib.request
    import urllib.error

    if not symbol_ids:
        return {}

    coin_ids = list(symbol_ids.values())
    id_to_symbols: dict[str, list[str]] = {}
    for sym, cid in symbol_ids.items():
        id_to_symbols.setdefault(cid, []).append(sym)

    ids_str = ",".join(coin_ids)
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd"

    headers = {"Accept": "application/json"}
    api_key = os.environ.get("COINGECKO_API_KEY", "")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key

    req = urllib.request.Request(url, headers=headers)
    result: dict[str, Decimal] = {}

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"WARNING: CoinGecko HTTP {e.code}: {error_body[:200]}")
        return result
    except Exception as e:
        print(f"WARNING: CoinGecko fetch failed: {e}")
        return result

    for coin_id, price_info in data.items():
        price_usd = price_info.get("usd")
        if price_usd is not None:
            for sym in id_to_symbols.get(coin_id, []):
                result[sym] = Decimal(str(price_usd))

    return result


def get_token_usd_price(symbol: str, price_map: dict[str, Decimal]) -> Decimal | None:
    """Get USD price for a token symbol.

    Checks direct CoinGecko map first, then stablecoin heuristic.
    Returns None if unknown.
    """
    if symbol in price_map:
        return price_map[symbol]
    if symbol.upper() in _STABLECOINS:
        return Decimal("1.0")
    return None


# ─────────────────────────────────────────────
# DECODE MULTICALL3 RESPONSE
# ─────────────────────────────────────────────

def decode_aggregate3_response(return_hex: str) -> list[tuple[bool, str]]:
    """Decode aggregate3 return data.

    Returns: list of (success_bool, return_data_hex_with_0x_prefix)
    """
    raw = return_hex.removeprefix("0x")

    if len(raw) < 128:
        raise ValueError(f"aggregate3 response too short: {len(raw)} hex chars")

    # Slot 0 (0-63): totalGasUsed — skip
    # Slot 1 (64-127): offset to results array (in bytes)
    array_offset_bytes = int(raw[64:128], 16)
    array_offset_hex = array_offset_bytes * 2

    # Array length at the offset position
    array_length = int(raw[array_offset_hex:array_offset_hex + 64], 16)

    results: list[tuple[bool, str]] = []
    # Each result tuple has 2 slots: success (bool) + data_offset
    tuple_start_hex = array_offset_hex + 64  # skip the length slot
    tuple_size_hex = 128  # 2 slots * 64 hex chars each

    for i in range(array_length):
        base = tuple_start_hex + i * tuple_size_hex

        # success bool (slot 0 of tuple)
        success_val = int(raw[base:base + 64], 16) != 0

        # data offset (slot 1 of tuple, in bytes from calldata start)
        data_offset_bytes = int(raw[base + 64:base + 128], 16)
        data_offset_hex = data_offset_bytes * 2

        # Data length and content
        data_len = int(raw[data_offset_hex:data_offset_hex + 64], 16)
        data_start = data_offset_hex + 64
        data_end = data_start + data_len * 2

        return_data = "0x" + raw[data_start:data_end]
        results.append((success_val, return_data))

    return results


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("FETCH_PRICES — Multicall3 slot0 Price Feed — Sprint 34")
    print("=" * 60)
    started_at = datetime.now(timezone.utc).isoformat() + "Z"
    print(f"Started: {started_at}")

    # Load RPC URL
    rpc_url = os.environ.get("BASE_RPC_HTTP", "")
    if not rpc_url:
        # Free public RPC — use Alchemy/Infura key if rate-limited:
        #   BASE_RPC_HTTP=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
        rpc_url = "https://base.llamarpc.com"
    print(f"RPC: {rpc_url}")

    # Load registry
    if not REGISTRY_PATH.exists():
        print(f"FATAL: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    registry = json.loads(REGISTRY_PATH.read_text())
    # registry.json is a top-level list [{pool}, ...]
    pools = registry if isinstance(registry, list) else registry.get("pools", [])
    print(f"Pools in registry: {len(pools)}")

    if not pools:
        print("FATAL: No pools in registry.")
        sys.exit(1)

    # Get current block number
    block_hex = rpc_call("eth_blockNumber", [], rpc_url)
    block_num = int(block_hex, 16)
    print(f"Current block: {block_num}")

    # Collect unique token symbols for CoinGecko
    all_symbols: set[str] = set()
    for pool in pools:
        t0 = pool.get("token0_symbol", "")
        t1 = pool.get("token1_symbol", "")
        if t0:
            all_symbols.add(t0)
        if t1:
            all_symbols.add(t1)

    # Build symbol -> coingecko_id mapping (skip stablecoins)
    symbols_to_fetch: dict[str, str] = {}
    for sym in all_symbols:
        if sym in _COINGECKO_IDS and sym not in _STABLECOINS:
            symbols_to_fetch[sym] = _COINGECKO_IDS[sym]

    # Fetch CoinGecko spot prices
    print(f"Fetching CoinGecko prices for {len(symbols_to_fetch)} tokens...")
    cg_prices = fetch_coingecko_spot_prices(symbols_to_fetch)
    print(f"CoinGecko prices fetched: {len(cg_prices)}")

    # Build Multicall3 aggregate3 payload
    targets: list[str] = []
    call_datas: list[str] = []

    for pool in pools:
        addr = pool.get("pool_address", "")
        if not addr:
            continue
        # slot0() takes no args, so calldata is just the 4-byte selector + 32 zero bytes
        targets.append(addr)
        call_datas.append(SLOT0_SELECTOR + "0" * 64)

    full_calldata = build_aggregate3_calldata(targets, call_datas)
    print(f"Multicall3 aggregate3: {len(targets)} calls")

    # Send single eth_call
    result = rpc_call(
        "eth_call",
        [{"to": MULTICALL3_ADDRESS, "data": full_calldata}, "latest"],
        rpc_url,
    )

    return_hex = result if isinstance(result, str) else ""
    if len(return_hex.removeprefix("0x")) < 128:
        print(f"FATAL: Multicall3 returned empty or invalid data")
        sys.exit(1)

    # Decode aggregate3 response
    mc_results = decode_aggregate3_response(return_hex)
    print(f"Multicall3 returned {len(mc_results)} results")

    slot0_ok = 0
    slot0_failed = 0
    priced_ok = 0
    no_usd_ref = 0

    output_pools: list[dict] = []

    for i, (success, return_data) in enumerate(mc_results):
        if i >= len(pools):
            break
        pool = pools[i]

        if not success:
            slot0_failed += 1
            output_pools.append({
                "pool_address": pool.get("pool_address", ""),
                "pair_name": pool.get("pair_name", ""),
                "sqrt_price_x96": None,
                "tick": None,
                "price_token0_in_usd": None,
                "price_token1_in_usd": None,
                "price_status": "slot0_failed",
                "fetched_at": started_at,
            })
            continue

        try:
            sqrt_price_x96, tick = decode_slot0(return_data)
        except ValueError as e:
            slot0_failed += 1
            output_pools.append({
                "pool_address": pool.get("pool_address", ""),
                "pair_name": pool.get("pair_name", ""),
                "sqrt_price_x96": None,
                "tick": None,
                "price_token0_in_usd": None,
                "price_token1_in_usd": None,
                "price_status": f"decode_error: {e}",
                "fetched_at": started_at,
            })
            continue

        slot0_ok += 1

        # Compute USD prices
        token0_symbol = pool.get("token0_symbol", "")
        token1_symbol = pool.get("token1_symbol", "")
        decimals0 = pool.get("decimals_token0", 18)
        decimals1 = pool.get("decimals_token1", 18)

        # Raw price: token1 per token0 (in display units)
        raw_price = compute_price(sqrt_price_x96, decimals0, decimals1)

        # Get token1 USD reference price
        token1_usd = get_token_usd_price(token1_symbol, cg_prices)

        if token1_usd is not None:
            price_token0_usd = raw_price * token1_usd
            price_token1_usd = token1_usd

            price_token0_str = str(price_token0_usd.quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP))
            price_token1_str = str(price_token1_usd.quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP))

            price_status = "ok"
            priced_ok += 1
        else:
            price_token0_str = None
            price_token1_str = None
            price_status = "no_usd_ref"
            no_usd_ref += 1

        output_pools.append({
            "pool_address": pool.get("pool_address", ""),
            "pair_name": pool.get("pair_name", ""),
            "sqrt_price_x96": str(sqrt_price_x96),
            "tick": tick,
            "price_token0_in_usd": price_token0_str,
            "price_token1_in_usd": price_token1_str,
            "price_status": price_status,
            "fetched_at": started_at,
        })

    # Build output
    output = {
        "fetched_at": started_at,
        "rpc_block": block_num,
        "pool_count": len(pools),
        "priced_count": priced_ok,
        "pools": output_pools,
    }

    # Atomic write
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = OUTPUT_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(output, indent=2))
    tmp_path.replace(OUTPUT_PATH)

    # Summary block (mandatory per .clinerules)
    print()
    print("=== FETCH_PRICES SUMMARY ===")
    print(f"block: {block_num}")
    print(f"pools_queried: {len(pools)}")
    print(f"slot0_ok: {slot0_ok}")
    print(f"slot0_failed: {slot0_failed}")
    print(f"priced_ok: {priced_ok}")
    print(f"no_usd_ref: {no_usd_ref}")
    print(f"output: data/prices/prices_latest.json")
    print("FETCH_PRICES COMPLETE.")


if __name__ == "__main__":
    main()