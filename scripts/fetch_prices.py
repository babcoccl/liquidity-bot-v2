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
    """
    Encode Multicall3 aggregate3((address,bool,bytes)[]) calldata.
    aggregate3 selector: 0x82ad56cb
    Each Call struct: (address target, bool allowFailure, bytes callData)
    Array of dynamic structs — each element is encoded with its own offset.
    """
    SELECTOR = "82ad56cb"
    n = len(targets)
    # The argument is a single dynamic array — encoded as:
    # [0x20 (offset to array)] [n (length)] [n offsets] [n struct bodies]
    #
    # Each struct body: [address 32B][bool 32B][offset-to-bytes 32B][bytes-length 32B][bytes-data padded]
    # Struct body size (without the bytes data): 3 * 32 = 96 bytes = fixed head
    # bytes field is dynamic, appended after the 3-word head.
    # Pre-compute each struct's encoded bytes blob and its total size
    struct_bodies: list[str] = []
    for i in range(n):
        addr = targets[i].lower().removeprefix("0x").zfill(40)
        cd = call_datas[i].removeprefix("0x")
        cd_len = len(cd) // 2  # byte length of callData
        cd_padded_len = ((cd_len + 31) // 32) * 32  # round up to 32-byte boundary
        cd_padded = cd.ljust(cd_padded_len * 2, "0")
        # Within the struct, bytes field is at offset 96 (3 words: addr + bool + offset)
        body = (
            addr.zfill(64) +           # address (32 bytes)
            f"{1:064x}" +              # allowFailure = true (32 bytes)
            f"{96:064x}" +             # offset to bytes within this struct = 96
            f"{cd_len:064x}" +         # bytes length
            cd_padded                   # bytes data padded
        )
        struct_bodies.append(body)
    # Each struct body size in bytes
    struct_sizes = [len(b) // 2 for b in struct_bodies]
    # Offsets to each struct from the start of the array data (after the length word)
    # First offset: n * 32 bytes (n offset words)
    offsets: list[int] = []
    current = n * 32
    for i in range(n):
        offsets.append(current)
        current += struct_sizes[i]
    hex_parts: list[str] = []
    hex_parts.append(f"{32:064x}")          # offset to array from calldata start
    hex_parts.append(f"{n:064x}")           # array length
    for off in offsets:
        hex_parts.append(f"{off:064x}")     # offset to each struct
    for body in struct_bodies:
        hex_parts.append(body)              # struct data
    return "0x" + SELECTOR + "".join(hex_parts)


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
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
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
    """
    Decode aggregate3 return: (Result[] returnData)
    where Result = (bool success, bytes returnData)
    Return format: [(success, hex_return_data), ...]
    """
    raw = return_hex.removeprefix("0x")
    # Word 0: offset to the array (in bytes from start of return data)
    array_offset = int(raw[0:64], 16) * 2   # convert bytes → hex chars
    # Word at array_offset: array length
    array_len = int(raw[array_offset:array_offset + 64], 16)
    # Offset table starts immediately after length word
    offset_table_start = array_offset + 64
    results: list[tuple[bool, str]] = []
    for i in range(array_len):
        # Each entry in the offset table: offset to the Result struct (from array_offset)
        struct_offset_hex = int(raw[offset_table_start + i * 64:offset_table_start + i * 64 + 64], 16) * 2
        struct_base = array_offset + 64 + struct_offset_hex
        # Result struct: [bool success (32B)][bytes offset (32B)] then bytes data
        success = int(raw[struct_base:struct_base + 64], 16) != 0
        bytes_offset = int(raw[struct_base + 64:struct_base + 128], 16) * 2
        bytes_start = struct_base + bytes_offset
        data_len = int(raw[bytes_start:bytes_start + 64], 16)
        data_start = bytes_start + 64
        data = raw[data_start:data_start + data_len * 2]
        results.append((success, "0x" + data))
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
        rpc_url = "https://mainnet.base.org"
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
        t0 = (pool.get("token0") or {}).get("symbol", "")
        t1 = (pool.get("token1") or {}).get("symbol", "")
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
        call_datas.append(SLOT0_SELECTOR)

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
        token0 = pool.get("token0") or {}
        token1 = pool.get("token1") or {}
        token0_symbol = token0.get("symbol", "")
        token1_symbol = token1.get("symbol", "")
        decimals0 = int(token0.get("decimals", 18))
        decimals1 = int(token1.get("decimals", 18))

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