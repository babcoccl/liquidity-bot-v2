"""CHECK THE GRAPH ENDPOINT CONNECTIVITY (SECONDARY SOURCE).

NOTE: fetch.py now uses GeckoTerminal as primary data source.
The Graph is retained as a fallback for when GeckoTerminal is
unavailable. Run this script to verify Graph indexers are healthy
before switching back.

Checks:
  1. THEGRAPH_API_KEY is loaded
  2. Subgraph endpoint responds (ping)
  3. liquidityPoolHourlySnapshots field present with collection args

Usage:
    python scripts/check_graph_endpoint.py

Exit code 0 = all checks passed.
Exit code 1 = one or more checks failed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SUBGRAPH_ID = "FUbEPQw1oMghy39fwWBFY5fE6MXPXZQtjncQy2cXdrNS"
GATEWAY_URL = "https://gateway.thegraph.com/api/{key}/subgraphs/id/{sub}"
TIMEOUT = 15


def _post(url: str, query: str) -> dict:
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, multipart/mixed",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Origin": "https://thegraph.com",
            "Referer": "https://thegraph.com/",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def main() -> int:
    failures: list[str] = []

    # CHECK 1: API key present
    key = os.environ.get("THEGRAPH_API_KEY", "")
    if not key:
        print("CHECK FAILED: THEGRAPH_API_KEY not set in environment or .env")
        return 1
    print(f"[1] KEY: SET (length={len(key)}, prefix={key[:6]})")

    url = GATEWAY_URL.format(key=key, sub=SUBGRAPH_ID)

    # CHECK 2: Ping subgraph
    try:
        data = _post(url, "{ _meta { block { number } } }")
        block = data.get("data", {}).get("_meta", {}).get("block", {}).get("number")
        print(f"[2] PING: OK (block={block})")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        failures.append(f"PING HTTP {e.code}: {body}")
        print(f"[2] PING: FAILED — HTTP {e.code}: {body}")
    except Exception as e:
        failures.append(f"PING {type(e).__name__}: {e}")
        print(f"[2] PING: FAILED — {type(e).__name__}: {e}")

    if failures:
        print("CHECK FAILED: cannot reach subgraph, aborting schema check")
        return 1

    # CHECK 3: Schema — find poolHourDatas field and its arg types
    try:
        schema_query = """{
          __schema {
            queryType {
              fields {
                name
                args { name type { name kind ofType { name kind } } }
              }
            }
          }
        }"""
        data = _post(url, schema_query)
        fields = data["data"]["__schema"]["queryType"]["fields"]

        # Match the PLURAL collection field (has where/orderBy/first args)
        # NOT the singular lookup field (has only id/block args)
        hour_field = None
        for f in fields:
            name_lower = f["name"].lower()
            if (
                "hourly" in name_lower
                and "pool" in name_lower
                and name_lower.endswith("snapshots")  # plural only
            ):
                # Confirm it has collection-style args (where or first or orderBy)
                arg_names = {a["name"] for a in f["args"]}
                if arg_names & {"where", "first", "orderBy"}:
                    hour_field = f
                    break

        if hour_field is None:
            failures.append("liquidityPoolHourlySnapshots field NOT found in schema")
            print("[3] SCHEMA: FAILED — no pool hourly field found")
            print("    Available pool fields:")
            for f in fields:
                if "pool" in f["name"].lower():
                    print(f"      {f['name']}")
        else:
            args = {}
            for a in hour_field["args"]:
                t = a["type"]
                type_name = t.get("name") or (t.get("ofType") or {}).get("name", "?")
                args[a["name"]] = type_name
            print(f"[3] SCHEMA: field={hour_field['name']} args={args}")

            # CHECK 4: Confirm collection-style args present
            # Messari subgraphs use nested `where` input for filters —
            # pool address and timestamp filters are inside the where object,
            # not as top-level args. Confirm `where` and `first` are present.
            has_where = "where" in args
            has_first = "first" in args
            has_order = "orderBy" in args

            print(f"[4] COLLECTION ARGS: where={has_where} first={has_first} orderBy={has_order}")

            if not has_where:
                failures.append(
                    f"Field {hour_field['name']} missing 'where' arg — "
                    "cannot filter by pool address or timestamp"
                )
                print("[4] COLLECTION ARGS: FAILED — 'where' arg not found")

    except Exception as e:
        failures.append(f"SCHEMA {type(e).__name__}: {e}")
        print(f"[3] SCHEMA: FAILED — {type(e).__name__}: {e}")

    if failures:
        print()
        for f in failures:
            print(f"CHECK FAILED: {f}")
        return 1

    print()
    print("CHECK PASSED: endpoint reachable, liquidityPoolHourlySnapshots confirmed, args identified")
    return 0


if __name__ == "__main__":
    sys.exit(main())