## Current Sprint: Sprint 34 — On-Chain Price Feed via Multicall3 slot0 (complete — awaiting YOU RUN)

**Goal**: Real-time price feed for all 268 registry pools via single Multicall3 RPC call.
**Decision**: GeckoTerminal dropped from architecture (rate-limited at 30 req/min free tier; incompatible with bot cycle time). `check_geckoterminal.py` retained as diagnostic only.

### What was added
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
# 1. Validate slot0 RPC path for top 3 pools
python scripts/check_slot0.py

# 2. If CHECK PASSED — run full price fetch
python scripts/fetch_prices.py

# 3. Commit
git add scripts/fetch_prices.py scripts/check_slot0.py data/prices/.gitkeep .gitignore memory/activeContext.md memory/known_issues.md memory/manifest.json
git commit -m "ADD fetch_prices.py + check_slot0.py: Multicall3 slot0 price feed. Sprint 34 complete."
```

---

## Recent Sprints

| Sprint | Title | Status |
|--------|-------|--------|
| 34 | On-Chain Price Feed via Multicall3 slot0 | complete — awaiting YOU RUN |
| 33 | Registry Population + OHLCV Schema | complete |
| 32 | Aerodrome Pool Discovery | complete |
| 31 | Sugar SDK Pipeline v2 | complete |