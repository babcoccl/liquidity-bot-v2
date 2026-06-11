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
    n = len(targets)
    func_sel = "b824b87c"

    tuples_start = 64
    blobs_start = tuples_start + n * (3 * 32)

    hex_parts: list[str] = []
    hex_parts.append(f"{32:064x}")
    hex_parts.append(f"{n:064x}")

    current_blob_offset = blobs_start

    for i in range(n):
        addr_hex = targets[i].lower().removeprefix("0x")
        hex_parts.append(_pad32(addr_hex))
        hex_parts.append("0" * 64)
        hex_parts.append(f"{current_blob_offset:064x}")

        cd_raw = call_datas[i].removeprefix("0x")
        total_data_hex = 64 + len(cd_raw)
        remainder = total_data_hex % 64
        if remainder:
            total_data_hex += 64 - remainder
        blob_bytes = total_data_hex // 2
        current_blob_offset += blob_bytes

    for cd in call_datas:
        raw = cd.removeprefix("0x")
        hex_parts.append(_bytes_length_prefix(raw))

    return "0x" + func_sel + "".join(hex_parts)


def decode_aggregate3_response(return_hex: str) -> list[tuple[bool, str]]:
    raw = return_hex.removeprefix("0x")
    if len(raw) < 128:
        raise ValueError(f"aggregate3 response too short: {len(raw)} hex chars")

    array_offset_bytes = int(raw[64:128], 16)
    array_offset_hex = array_offset_bytes * 2
    array_length = int(raw[array_offset_hex:array_offset_hex + 64], 16)

    results: list[tuple[bool, str]] = []
    tuple_start_hex = array_offset_hex + 64
    tuple_size_hex = 128

    for i in range(array_length):
        base = tuple_start_hex + i * tuple_size_hex
        success_val = int(raw[base:base + 64], 16) != 0
        data_offset_bytes = int(raw[base + 64:base + 128], 16)
        data_offset_hex = data_offset_bytes * 2
        data_len = int(raw[data_offset_hex:data_offset_hex + 64], 16)
        data_start = data_offset_hex + 64
        data_end = data_start + data_len * 2
        return_data = "0x" + raw[data_start:data_end]
        results.append((success_val, return_data))

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
        call_datas.append(SLOT0_SELECTOR + "0" * 64)

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