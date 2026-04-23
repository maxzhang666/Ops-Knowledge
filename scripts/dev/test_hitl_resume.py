"""End-to-end HITL test helper.

Does the boring parts for you:
 1. Logs in with username/password → gets a JWT token
 2. Lists workflows, finds the one you reference
 3. Finds the most-recent execution with status=="waiting"
 4. POSTs the resume endpoint with your value

Usage:
    .venv/bin/python scripts/test_hitl_resume.py \\
        --host http://localhost:8200 \\
        --username admin --password 'yourpass' \\
        --workflow-name '你的工作流名字' \\
        --value '{"approved": true}'

Or if you already know IDs:
    .venv/bin/python scripts/test_hitl_resume.py \\
        --host http://localhost:8200 \\
        --token <JWT> \\
        --workflow-id <WF_UUID> --execution-id <EXEC_UUID> \\
        --value 'approved'

The resume ``--value`` is parsed as JSON if it starts with ``{`` / ``[``
/ ``"`` / is ``true/false/null`` / a number; otherwise taken as a string.
"""
from __future__ import annotations

import argparse
import json
import sys

import httpx


def parse_value(raw: str):
    if raw == "":
        return None
    s = raw.strip()
    first = s[0] if s else ""
    if first in '{["' or s in ("true", "false", "null") or first.isdigit() or first == "-":
        try:
            return json.loads(s)
        except Exception:
            pass
    return raw  # fallback: treat as literal string


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="http://localhost:8200",
                    help="API base URL (no trailing slash)")
    ap.add_argument("--username")
    ap.add_argument("--password")
    ap.add_argument("--token",
                    help="Use an existing JWT instead of --username/--password")
    ap.add_argument("--workflow-name",
                    help="Find workflow by name (if --workflow-id not given)")
    ap.add_argument("--workflow-id")
    ap.add_argument("--execution-id",
                    help="Specific execution to resume. If omitted, picks the "
                         "most-recent waiting execution for --workflow-id.")
    ap.add_argument("--value", required=True,
                    help="Resume value passed to interrupt()")
    args = ap.parse_args()

    api = f"{args.host}/api/v1"
    client = httpx.Client(timeout=30.0)

    # --- auth ---
    if args.token:
        token = args.token
    else:
        if not (args.username and args.password):
            print("need --token or --username+--password")
            return 2
        r = client.post(
            f"{api}/auth/login",
            json={"username": args.username, "password": args.password},
        )
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            print(f"login returned no access_token: {r.text}")
            return 1
    headers = {"Authorization": f"Bearer {token}"}
    print(f"auth ok")

    # --- resolve workflow_id ---
    wf_id = args.workflow_id
    if not wf_id:
        if not args.workflow_name:
            print("need --workflow-id or --workflow-name")
            return 2
        r = client.get(f"{api}/workflow", headers=headers)
        r.raise_for_status()
        candidates = [w for w in r.json() if w.get("name") == args.workflow_name]
        if not candidates:
            print(f"no workflow named '{args.workflow_name}'")
            return 1
        wf_id = candidates[0]["id"]
        print(f"workflow: {args.workflow_name} → {wf_id}")

    # --- resolve execution_id ---
    exec_id = args.execution_id
    if not exec_id:
        r = client.get(f"{api}/workflow/{wf_id}/executions",
                       headers=headers, params={"page_size": "20"})
        r.raise_for_status()
        rows = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        waiting = [x for x in rows if x.get("status") == "waiting"]
        if not waiting:
            print("no waiting execution found for this workflow")
            print("(did the workflow actually hit a human_approval node?)")
            return 1
        exec_id = waiting[0]["id"]
        print(f"waiting execution: {exec_id}")

    # --- call resume ---
    value = parse_value(args.value)
    print(f"resume value (parsed): {value!r}")

    r = client.post(
        f"{api}/workflow/{wf_id}/executions/{exec_id}/resume",
        headers={**headers, "Content-Type": "application/json"},
        json={"value": value},
    )
    if r.status_code >= 400:
        print(f"FAIL {r.status_code}: {r.text}")
        return 1
    print(f"resume accepted ({r.status_code}): {r.json()}")
    print()
    print(f"→ reconnect WS to see the continuation:")
    print(f"  {args.host.replace('http', 'ws')}/api/v1/workflow/{wf_id}/executions/{exec_id}/events?token=<YOUR_TOKEN>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
