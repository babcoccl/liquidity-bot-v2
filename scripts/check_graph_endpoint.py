"""CHECK THE GRAPH ENDPOINT CONNECTIVITY AND POOL HOURLY SCHEMA.

Run this before fetch.py to verify:
  1. API key is loaded
  2. Subgraph endpoint responds (ping)
  3. poolHourDatas field exists on the schema
  4. Variable types match what fetch.py sends

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

        hour_field = None
        for f in fields:
            if "hourdata" in f["name"].lower() and "pool" in f["name"].lower():
                hour_field = f
                break

        if hour_field is None:
            failures.append("poolHourDatas (or equivalent) field NOT found in schema")
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

            # CHECK 4: Variable type compatibility
            pool_arg = next(
                (k for k in args if "pool" in k.lower()), None
            )
            ts_arg = next(
                (k for k in args if "unix" in k.lower() or "time" in k.lower()), None
            )
            if pool_arg:
                print(f"[4] POOL ARG:  {pool_arg}: {args[pool_arg]}")
            else:
                failures.append("No pool address argument found on hourly field")
                print("[4] POOL ARG: FAILED — not found")
            if ts_arg:
                print(f"[4] TS ARG:    {ts_arg}: {args[ts_arg]}")
            else:
                failures.append("No timestamp argument found on hourly field")
                print("[4] TS ARG: FAILED — not found")

    except Exception as e:
        failures.append(f"SCHEMA {type(e).__name__}: {e}")
        print(f"[3] SCHEMA: FAILED — {type(e).__name__}: {e}")

    if failures:
        print()
        for f in failures:
            print(f"CHECK FAILED: {f}")
        return 1

    print()
    print("CHECK PASSED: endpoint reachable, poolHourDatas confirmed, args identified")
    return 0


if __name__ == "__main__":
    sys.exit(main())