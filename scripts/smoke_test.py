"""Smoke test — verify the running server can complete a trivial task.

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --host http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx


async def smoke(host: str) -> int:
    print(f"→ Smoke test against {host}")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Health-ish: list tasks
        try:
            r = await client.get(f"{host}/api/tasks")
            r.raise_for_status()
        except Exception as e:
            print(f"✗ Cannot reach /api/tasks: {e}")
            return 1
        print("✓ /api/tasks reachable")

        # 2. Submit a tiny task
        r = await client.post(
            f"{host}/api/run",
            json={
                "goal": "Visit https://httpbin.org/get and extract the JSON response.",
                "headless": True,
                "use_vision": False,
            },
        )
        r.raise_for_status()
        task_id = r.json()["task_id"]
        print(f"✓ Submitted task {task_id}")

        # 3. Poll for completion (max 3 min)
        deadline = time.time() + 180
        while time.time() < deadline:
            r = await client.get(f"{host}/api/tasks/{task_id}")
            r.raise_for_status()
            status = r.json()["status"]
            print(f"   ...{status}")
            if status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(5)
        else:
            print("✗ Timed out waiting for task")
            return 1

        result = r.json()
        if result["status"] != "succeeded":
            print(f"✗ Task did not succeed: {json.dumps(result, indent=2)[:500]}")
            return 1

        verdict = result.get("result") or {}
        if not verdict.get("success"):
            print(f"✗ Verifier returned success=false: {verdict.get('reason')}")
            return 1

        print(f"✓ Task succeeded with confidence={verdict.get('confidence')}")
        print(f"  Reason: {verdict.get('reason')}")
        return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://127.0.0.1:8000")
    args = p.parse_args()
    sys.exit(asyncio.run(smoke(args.host)))


if __name__ == "__main__":
    main()
