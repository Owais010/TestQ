"""Integration test — runs a real GitHub repo through the Phase 1 pipeline."""

import httpx
import time
import json
import sys

BASE = "http://localhost:8000"
REPO = "https://github.com/nicolo-ribaudo/tc39-proposal-for-in-order"
BRANCH = "main"

client = httpx.Client(timeout=120.0)

# Create test run
print("=== Creating test run ===")
r = client.post(f"{BASE}/api/test-runs", json={
    "repository_url": REPO,
    "branch": BRANCH,
})
print(f"Status: {r.status_code}")
data = r.json()
run_id = data["id"]
print(f"Run ID: {run_id[:8]}")
print(f"Initial status: {data['status']}")

# Poll for status
print()
print("=== Polling status ===")
for i in range(40):
    time.sleep(5)
    r2 = client.get(f"{BASE}/api/test-runs/{run_id}")
    sd = r2.json()
    status = sd["status"]
    print(f"[{(i+1)*5:3d}s] Status: {status}")

    if status in ("READY", "COMPLETED", "FAILED", "CANCELLED"):
        print()
        if status == "FAILED":
            print(f"Failure stage: {sd.get('failure_stage')}")
            print(f"Failure reason: {sd.get('failure_reason', '')[:300]}")
        if sd.get("detected_config"):
            cfg = sd["detected_config"]
            print(f"Detected framework: {cfg.get('framework')}")
            print(f"Detected language: {cfg.get('language')}")
            print(f"Detected PM: {cfg.get('package_manager')}")
            print(f"Install: {cfg.get('install_command')}")
            print(f"Build: {cfg.get('build_command')}")
            print(f"Start: {cfg.get('start_command')}")
            print(f"Port: {cfg.get('expected_port')}")
        print(f"Progress: {json.dumps(sd.get('progress', {}), indent=2)}")
        break

# Get logs
print()
print("=== Logs ===")
r3 = client.get(f"{BASE}/api/test-runs/{run_id}/logs")
logs = r3.json().get("logs", [])
for log in logs[-20:]:
    print(f"[{log['source']:10}] {log['level']:5} | {log['message'][:150]}")
