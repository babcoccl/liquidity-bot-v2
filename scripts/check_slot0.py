#!/usr/bin/env python3
"""
Sprint 34 diagnostic: validate slot0() via Multicall3 for top 3 pools.

Loads registry/registry.json, picks the first 3 pools by list order (top TVL),
sends a Multicall3 aggregate3 call with slot0(), decodes and prints results.

Usage:
    python scripts/check_slot0.py

Exit codes:
    0 — CHECK PASSED
    1 — CHECK FAILED
"""

import json
import os
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────
# CONSTANTS (shared with fetch_prices.py)
# ─────────────────────────────────────────────

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
SLOT0_SELECTOR = "0x3850c7bd"
REGISTRY_PATH = Path("registry/registry.json")


# ─────────────────────────────────────────────
# ABI HELPERS (identical to fetch_prices.py)
# ─────────────────────────────────────────────

def _pad32(value_hex: str) -> str:
    return value_hex.zfill(64)


def _bytes_length_prefix(data_hex: str) -> str:
    parts = [f"{len(data_hex)//2:064x}", data_hex]
    total_len = 64 + len(data_hex)
    remainder = total_len % 64
    if remainder:
        parts.append("0" * (64 - remainder))
    return "".join(parts)


def decode_slot0(return_data: str) -> tuple[int, int]:
    raw = return_data.removeprefix("0x")
    if len(raw) < 128:
        raise ValueError(f"slot0 return data too short: {len(raw)} hex chars")

    sqrt_price_x96 = int(raw[:64], 16)

    tick_raw = int(raw[64:128], 16)
    if tick_raw >= 2**23:
        tick = tick_raw - 2**24
    else:
        tick = tick_raw

    return sqrt_price_x96, tick


def compute_price(sqrt_price_x96: int, decimals0: int, decimals1: int) -> Decimal:
    Q96 = Decimal(2**96)
    sqrt_ratio = Decimal(sqrt_price_x96) / Q96
    price_ratio = sqrt_ratio * sqrt_ratio
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
            "0" * 64 +                 # allowFailure = false (32 bytes)
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
# RPC (urllib only)
# ─────────────────────────────────────────────

def rpc_call(method: str, params: list, rpc_url: str) -> dict:
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
        with urllib.request.urlopen(req, timeout=15) as resp:
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
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("CHECK_SLOT0 — Multicall3 slot0 diagnostic (top 3 pools)")
    print("=" * 60)

    rpc_url = os.environ.get("BASE_RPC_HTTP", "")
    if not rpc_url:
        # Free public RPC endpoints — replace with Alchemy/Infura key if rate-limited
        #   BASE_RPC_HTTP=https://base-mainnet.g.alchemy.com/v2/YOUR_KEY
        rpc_url = "https://mainnet.base.org"
    print(f"RPC: {rpc_url}")

    # Load registry
    if not REGISTRY_PATH.exists():
        print(f"FATAL: Registry not found at {REGISTRY_PATH}")
        print("CHECK FAILED: registry.json missing")
        sys.exit(1)

    registry = json.loads(REGISTRY_PATH.read_text())
    # registry.json is a top-level list [{pool}, ...]
    pools = registry if isinstance(registry, list) else registry.get("pools", [])
    if not pools:
        print("FATAL: No pools in registry.")
        print("CHECK FAILED: empty registry")
        sys.exit(1)

    # Pick top 3 by list order (registry is sorted by TVL descending)
    check_pools = pools[:3]
    print(f"Registry has {len(pools)} pools. Checking first {len(check_pools)}...")
    print()

    targets: list[str] = []
    call_datas: list[str] = []

    for pool in check_pools:
        addr = pool.get("pool_address", "")
        name = pool.get("pair_name", "unknown")
        print(f"  Pool #{len(targets)+1}: {name} @ {addr[:20]}...")
        targets.append(addr)
        call_datas.append(SLOT0_SELECTOR)

    # Build & send Multicall3 aggregate3
    full_calldata = build_aggregate3_calldata(targets, call_datas)

    result = rpc_call(
        "eth_call",
        [{"to": MULTICALL3_ADDRESS, "data": full_calldata}, "latest"],
        rpc_url,
    )

    return_hex = result if isinstance(result, str) else ""
    if len(return_hex.removeprefix("0x")) < 128:
        print()
        print("CHECK FAILED: Multicall3 returned empty or invalid data")
        sys.exit(1)

    mc_results = decode_aggregate3_response(return_hex)
    ok_count = 0

    print()
    for i, (success, return_data) in enumerate(mc_results):
        pool = check_pools[i]
        name = pool.get("pair_name", "unknown")
        decimals0 = pool.get("decimals_token0", 18)
        decimals1 = pool.get("decimals_token1", 18)

        if not success:
            print(f"  [{i+1}] {name}: SLOT0 FAILED (call returned failure)")
            continue

        try:
            sqrt_price_x96, tick = decode_slot0(return_data)
            raw_ratio = compute_price(sqrt_price_x96, decimals0, decimals1)

            ratio_str = str(raw_ratio.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
            print(f"  [{i+1}] {name}:")
            print(f"      sqrtPriceX96: {sqrt_price_x96}")
            print(f"      tick:         {tick}")
            print(f"      raw ratio (token1/token0): {ratio_str}")
            ok_count += 1
        except ValueError as e:
            print(f"  [{i+1}] {name}: DECODE ERROR — {e}")

    print()
    if ok_count == len(check_pools):
        print(f"CHECK PASSED: slot0 readable for {ok_count}/{len(check_pools)} pools")
        sys.exit(0)
    else:
        print(f"CHECK FAILED: only {ok_count}/{len(check_pools)} pools returned valid slot0 data")
        sys.exit(1)


if __name__ == "__main__":
    main()