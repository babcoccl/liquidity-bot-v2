"""CHECK THAT data/historical/ AND data/prices/ HAVE REAL RECORDS.

Run this after fetch.py to verify all files are non-empty before
running run_backtest.py.

Usage:
    python scripts/check_data_files.py

Exit code 0 = all files present with N > 0 records.
Exit code 1 = missing files or N=0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HISTORICAL_DIR = Path("data/historical")
PRICES_DIR = Path("data/prices")

REQUIRED_HISTORICAL = ["USDC-WETH.json", "WETH-cbBTC.json", "USDC-USDT.json"]
REQUIRED_PRICES = ["WETH.json", "USDC.json", "USDT.json", "cbBTC.json"]


def check_dir(directory: Path, required: list[str]) -> list[str]:
    failures: list[str] = []
    for fname in required:
        fpath = directory / fname
        if not fpath.exists():
            failures.append(f"MISSING: {fpath}")
            print(f"  [{fname}] MISSING")
            continue
        try:
            data = json.loads(fpath.read_text())
            n = len(data.get("records", []))
            status = "OK" if n > 0 else "EMPTY"
            print(f"  [{fname}] {status} — N={n}")
            if n == 0:
                failures.append(f"EMPTY: {fpath} has 0 records")
        except Exception as e:
            failures.append(f"PARSE ERROR: {fpath}: {e}")
            print(f"  [{fname}] PARSE ERROR: {e}")
    return failures


def main() -> int:
    failures: list[str] = []

    print("=== HISTORICAL ===")
    failures += check_dir(HISTORICAL_DIR, REQUIRED_HISTORICAL)

    print("=== PRICES ===")
    failures += check_dir(PRICES_DIR, REQUIRED_PRICES)

    print()
    if failures:
        for f in failures:
            print(f"CHECK FAILED: {f}")
        return 1

    print("CHECK PASSED: all required data files present with N > 0 records")
    return 0


if __name__ == "__main__":
    sys.exit(main())