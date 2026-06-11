#!/usr/bin/env python3
"""Quick diagnostic: call slot0() directly on one pool via eth_call."""

import json, os, sys
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError: pass

rpc_url = os.environ.get("BASE_RPC_HTTP", "https://mainnet.base.org")
pool_addr = "0xcdac0d6c6c59727a65"  # WETH-USDC-30 (partial)
# Full address from registry
import json as j
registry = j.load(open("registry/registry.json"))
pool = registry[2]  # WETH-USDC-30
addr = pool["pool_address"]

SLOT0_SEL = "0x3850c7bd"
QUOTER_SEL = "0x75b5d4fc"  # quoteExactInputSingle for UniswapV3QuoterV2

def rpc(method, params):
    import urllib.request, urllib.error
    payload = json.dumps({"jsonrpc":"2.0","method":method,"params":params,"id":1}).encode()
    req = urllib.request.Request(rpc_url, data=payload, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
    except Exception as e:
        print(f"RPC error: {e}"); sys.exit(1)
    if "error" in body:
        print(f"RPC error: {body['error']}"); sys.exit(1)
    return body["result"]

# Direct slot0 call
print(f"Testing direct slot0() on {addr}")
result = rpc("eth_call", [{"to": addr, "data": SLOT0_SEL}, "latest"])
print(f"  raw result: {result[:200] if result else 'None'}")

# Try getting code at address (is it a contract?)
code = rpc("eth_getCode", [addr, "latest"])
print(f"  has code: {len(code.removeprefix('0x')) > 0}")
print(f"  code length: {len(code.removeprefix('0x'))//2} bytes")

# Try the pool's actual interface - check if it has slot0 at a different selector
# Aerodrome v2 pools use IConcentratedLiquidityNFT which may have different selectors
# Let's try observing the pool via the factory/router pattern
print()
print("Trying eth_call with just 4 bytes of slot0 selector padded to 32:")
result2 = rpc("eth_call", [{"to": addr, "data": SLOT0_SEL + "0" * 64}, "latest"])
print(f"  raw result: {result2[:200] if result2 else 'None'}")

# Check code size - if it's a proxy, we need to check the implementation
impl = rpc("eth_getStorageAt", [addr, "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc", "latest"])
print(f"  eip-1967 impl slot: {impl}")

# Try calling via Multicall3 with a single call to see raw revert data
MULTICALL = "0xcA11bde05977b3631167028862bE2a173976CA11"
try:
    # tryBlockAndAggregate with allowFailure=true
    calldata = (
        "ax91d81d4" +  # tryBlockAndAggregate((address,bytes)[])
        "0020" +       # offset to array
        "0000000000000000000000000000000000000000000000000000000000000001" +  # 1 call
        "0000000000000000000000000000000000000000000000000000000000000020" +  # offset to first call
        addr.lower().removeprefix("0x").zfill(64) +  # target address
        "0000000000000000000000000000000000000000000000000000000000000040" +  # offset to data
        "0000000000000000000000000000000000000000000000000000000000000004" +  # data length = 4
        SLOT0_SEL.removeprefix("0x") + "0" * 60  # selector padded to 32 bytes
    )
    mc_result = rpc("eth_call", [{"to": MULTICALL, "data": calldata}, "latest"])
    print(f"\nMulticall tryBlockAndAggregate result: {mc_result[:300] if mc_result else 'None'}")
except Exception as e:
    print(f"Multicall test error: {e}")

print("\nDEBUG DONE.")