#!/usr/bin/env python3
"""
Sprint 22D/33-Pre: Verify slot0() is callable for every CL pool in the registry.

Resolution chain for SlipstreamCL pools:
  registry.pool_address (LP token) -> pool_reference.gauge_address -> pool() -> CLPool -> slot0()

For vAMM pools (gauge has no pool() function), slot0() is not applicable — they use getPrices().

Usage:
    python scripts/check_slot0.py

Env vars (loaded from .env):
    BASE_RPC_HTTP   — Base L2 HTTP RPC endpoint (required)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

SLOT0_SELECTOR = "0x3850c7bd"          # slot0()
POOL_SELECTOR  = "0x16f0115b"           # pool() -> returns address (SlipstreamCL gauge only)
REGISTRY_PATH  = Path("registry/registry.json")
POOL_REF_PATH  = Path("memory/pool_reference.json")

# Rate limiting: Base public RPC is very restrictive (429 after ~5 calls)
# 268 pools * 2 calls each = 536 calls; need ~0.5s spacing to survive
RPC_DELAY      = 0.5    # seconds between calls

# Fallback RPC endpoints — try each until one works
FALLBACK_RPCS = [
    "https://base-mainnet.public.blastapi.io",
    "https://1rpc.io/base",
    "https://base.gateway.tenderly.co",
    "https://base.drpc.org",
    "https://mainnet.base.org",
]


# ─────────────────────────────────────────────
# RPC HELPER (urllib only)
# ─────────────────────────────────────────────

def rpc_call(method: str, params: list, rpc_url: str, _fatal: bool = True, _retry: int = 0) -> dict | None:
    """Send a JSON-RPC call via urllib. Returns the result or None on revert.

    When _fatal=False, contract reverts return None instead of exiting.
    Network-level failures are retried with exponential backoff (up to 3 times).
    Rate-limit (429) errors trigger longer backoff.
    """
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
        # 429 rate limit — retry with backoff
        if e.code == 429 and _retry < 3:
            wait = (1 << _retry) * 2  # 2s, 4s, 8s
            print(f"  RATE LIMITED (429), waiting {wait}s... (attempt {_retry+1}/3)")
            time.sleep(wait)
            return rpc_call(method, params, rpc_url, _fatal, _retry + 1)
        print(f"RPC HTTP {e.code}: {error_body[:300]}")
        sys.exit(1)
    except Exception as e:
        if _retry < 3:
            wait = (1 << _retry) * 1
            time.sleep(wait)
            return rpc_call(method, params, rpc_url, _fatal, _retry + 1)
        print(f"RPC call failed after retries: {e}")
        sys.exit(1)

    if "error" in body:
        err = body["error"]
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        # Contract reverts are not fatal when _fatal=False
        if not _fatal and ("revert" in msg.lower() or "execution reverted" in msg.lower()):
            return None
        print(f"RPC error: {err}")
        sys.exit(1)

    return body.get("result")


# ─────────────────────────────────────────────
# CLPOOL RESOLUTION
# ─────────────────────────────────────────────

def build_calldata(selector: str, padded: bool = True) -> str:
    """Encode calldata from a 4-byte selector."""
    return selector + ("00" * 32 if padded else "")


def decode_address(return_data: str) -> str:
    """Decode a single address from ABI-encoded return data (32 bytes, right-aligned)."""
    raw = return_data.removeprefix("0x")
    addr_hex = raw[-40:].zfill(40)
    return "0x" + addr_hex


def call_pool_on_gauge(gauge_addr: str, rpc_url: str) -> str | None:
    """Call pool() on a gauge contract. Returns CLPool address or None."""
    calldata = build_calldata(POOL_SELECTOR)
    ret = rpc_call("eth_call", [{"to": gauge_addr, "data": calldata}, "latest"], rpc_url, _fatal=False)
    time.sleep(RPC_DELAY)
    if ret and len(ret.removeprefix("0x")) >= 40:
        return decode_address(ret)
    return None


def call_slot0(target: str, rpc_url: str) -> int | None:
    """Call slot0() on a CLPool. Returns sqrtPriceX96 or None."""
    calldata = build_calldata(SLOT0_SELECTOR)
    ret = rpc_call("eth_call", [{"to": target, "data": calldata}, "latest"], rpc_url, _fatal=False)
    time.sleep(RPC_DELAY)
    if ret and len(ret.removeprefix("0x")) >= 64:
        return int(ret.removeprefix("0x")[:64], 16)
    return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("CHECK_SLOT0 — Verify slot0() readability for CL pools")
    print("=" * 60)

    # Find a working RPC endpoint
    candidates = [os.environ.get("BASE_RPC_HTTP", ""), "https://base.llamarpc.com"] + FALLBACK_RPCS
    candidates = [c for c in candidates if c]  # drop empty
    rpc_url = None

    import urllib.request as _ur
    for candidate in candidates:
        try:
            probe = json.dumps({"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}).encode()
            req = _ur.Request(candidate, data=probe, headers={"Content-Type":"application/json"})
            with _ur.urlopen(req, timeout=10) as r:
                res = json.loads(r.read().decode())
            if "result" in res:
                rpc_url = candidate
                chain_id = res["result"]
                print(f"RPC OK: {candidate} (chainId={chain_id})")
                break
        except Exception:
            continue

    if not rpc_url:
        print("FATAL: no working RPC endpoint found")
        sys.exit(1)

    # Load registry
    if not REGISTRY_PATH.exists():
        print(f"FATAL: Registry not found at {REGISTRY_PATH}")
        sys.exit(1)

    registry = json.loads(REGISTRY_PATH.read_text())
    pools = registry if isinstance(registry, list) else registry.get("pools", [])
    print(f"Pools in registry: {len(pools)}")

    # Build lookup: lp_address -> gauge_address from pool_reference.json
    gauge_map: dict[str, str] = {}  # lp_addr.lower() -> gauge_addr
    if POOL_REF_PATH.exists():
        pr_data = json.loads(POOL_REF_PATH.read_text())
        pr_pools = pr_data.get("pools", [])
        for pr_pool in pr_pools:
            pa = (pr_pool.get("pool_address") or "").lower()
            ga = (pr_pool.get("gauge_address") or "").lower()
            if pa and ga and ga != "not_found":
                gauge_map[pa] = ga
        print(f"Pool reference loaded: {len(gauge_map)} entries with gauge addresses")
    else:
        print(f"WARN: pool_reference.json not found at {POOL_REF_PATH}")

    # Collect unique pool addresses from registry that have gauge mappings
    lp_addrs = []
    pool_gauge_map: dict[str, str] = {}  # lp_addr -> gauge_addr
    for pool in pools:
        addr = (pool.get("pool_address") or "").lower()
        if not addr:
            continue
        if addr not in pool_gauge_map:
            lp_addrs.append(addr)
            ga = gauge_map.get(addr, "")
            if ga:
                pool_gauge_map[addr] = ga

    print(f"Unique registry addresses with gauge mapping: {len(lp_addrs)}")

    # Step 1 — Resolve CLPool via pool() on each gauge
    cl_pool_map: dict[str, str] = {}   # lp_addr -> cl_pool_addr
    vamm_count = 0
    unresolved = 0

    print("\nResolving CLPool addresses via pool() on gauge contracts...")
    for idx, lp_addr in enumerate(lp_addrs):
        gauge_addr = pool_gauge_map.get(lp_addr, "")
        if not gauge_addr:
            unresolved += 1
            continue

        cl_pool = call_pool_on_gauge(gauge_addr, rpc_url)
        if cl_pool:
            cl_pool_map[lp_addr] = cl_pool
            short_lp = lp_addr[:10] + "..."
            short_cl = cl_pool[:10] + "..."
            print(f"  [{idx+1}/{len(lp_addrs)}] {short_lp} -> gauge -> CLPool {short_cl}")
        else:
            vamm_count += 1

    print(f"\nResolved {len(cl_pool_map)} CL pools, {vamm_count} vAMM (no pool()), {unresolved} unmapped")

    # Step 2 — Call slot0() on resolved CLPool addresses
    ok = 0
    failed = 0
    results = []

    print(f"\nCalling slot0() on {len(cl_pool_map)} CL pools...")
    for idx, (lp_addr, cl_pool) in enumerate(cl_pool_map.items()):
        sqrt_price = call_slot0(cl_pool, rpc_url)
        if sqrt_price is not None:
            ok += 1
            short_lp = lp_addr[:10] + "..."
            print(f"  [{idx+1}/{len(cl_pool_map)}] OK: {short_lp} -> sqrtPriceX96={sqrt_price}")
        else:
            failed += 1
            short_lp = lp_addr[:10] + "..."
            short_cl = cl_pool[:10] + "..."
            print(f"  FAIL: {short_lp} -> CLPool {short_cl}: slot0() reverted")

    # Summary
    total_cl = len(cl_pool_map)
    print()
    print("=== CHECK_SLOT0 SUMMARY ===")
    print(f"pools_in_registry:     {len(pools)}")
    print(f"unique_addresses:      {len(lp_addrs)}")
    print(f"cl_pools_resolved:     {total_cl}")
    print(f"vamm_skipped:          {vamm_count}")
    print(f"unmapped_skipped:      {unresolved}")
    print(f"slot0_ok:              {ok}")
    print(f"slot0_failed:          {failed}")

    if ok == total_cl and total_cl > 0:
        print(f"CHECK PASSED: slot0 readable for {ok}/{total_cl} pools.")
        sys.exit(0)
    elif total_cl == 0:
        print("CHECK FAILED: no CL pools resolved — registry may contain only vAMM pools.")
        sys.exit(1)
    else:
        print(f"CHECK FAILED: slot0 only readable for {ok}/{total_cl} pools.")
        sys.exit(1)


if __name__ == "__main__":
    main()