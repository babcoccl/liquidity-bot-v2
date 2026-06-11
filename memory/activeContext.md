## Current Sprint: Sprint 34 — On-Chain Price Feed via Multicall3 slot0 (BLOCKED — registry rebuild required)

**Goal**: Real-time price feed for all CL registry pools via single Multicall3 RPC call.
**Decision**: GeckoTerminal dropped from architecture (rate-limited at 30 req/min free tier; incompatible with bot cycle time). `check_geckoterminal.py` retained as diagnostic only.

### BLOCKER: Registry contains vAMM pools, not CL pools

**Root cause**: `is_cl_pool()` in `scripts/fetch_aerodrome_pools.py` used `CL_TYPE = -1`, which is the volatile vAMM type. The filter was inverted — it selected vAMM pools instead of CL pools. This resulted in a registry of 268 vAMM pool addresses, making `check_slot0.py` fail (slot0 is a CL-only method).

**Fix applied**: Changed `is_cl_pool()` to check `type > 0`. Slipstream CL pools have `type > 0` (value equals tick_spacing, e.g., 1, 5, 30). `type == -1` is volatile vAMM, `type == 0` is stable sAMM — both are now correctly excluded.

**Impact**: The entire registry must be rebuilt from scratch:
1. Re-fetch pools with corrected filter → `memory/pool_reference_raw.json`
2. Re-build pool reference → `memory/pool_reference.json`
3. Re-populate registry → `registry/registry.json`
4. Then `check_slot0.py` will succeed on actual CL addresses

### What was added (Sprint 34)
- `scripts/fetch_prices.py` — Multicall3 slot0 decoder, outputs `data/prices/prices_latest.json`
- `scripts/check_slot0.py` — Validates slot0 RPC call for top 3 pools before full fetch
- `data/prices/.gitkeep` — Directory placeholder; `*.json` output is gitignored

### Price formula
```
price_token1_per_token0 = (sqrtPriceX96 / 2^96)^2
price_token0_in_usd = price_token1_per_token0 * (10^dec0 / 10^dec1) * token1_usd_price
```

### Price status codes
- `"ok"` — slot0 succeeded, CoinGecko USD ref available for token1
- `"no_usd_ref"` — slot0 succeeded but token1 has no CoinGecko mapping (not an error)
- `"slot0_failed"` — on-chain call returned success=false

### manifest.json fix
Sprint 33 left manifest.json corrupted (trailing comma + orphaned `{` at line 446). Fixed via Python script: truncated to last valid component, rebuilt with proper JSON structure. Validated: `json.load()` passes.

---

## Next Actions — YOU RUN (in order)

```bash
# 1. Re-fetch pools with corrected is_cl_pool() filter
python scripts/fetch_aerodrome_pools.py

# 2. Re-build pool reference from raw data
python scripts/build_pool_reference.py

# 3. Re-populate registry with correct CL addresses
python scripts/populate_registry.py

# 4. Validate slot0 RPC path for top 3 pools (must pass now)
python scripts/check_slot0.py

# 5. If CHECK PASSED — run full price fetch
python scripts/fetch_prices.py
```

---

## Recent Sprints

| Sprint | Title | Status |
|--------|-------|--------|
| 34 | On-Chain Price Feed via Multicall3 slot0 | BLOCKED — registry rebuild required |
| 33Pre | Pool Fetch — is_cl_pool fix (type > 0) | complete |
| 33 | Registry Population + OHLCV Schema | needs rebuild |
| 32 | Aerodrome Pool Discovery | needs rebuild |
| 31 | Sugar SDK Pipeline v2 | complete |