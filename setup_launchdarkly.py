"""One-time LaunchDarkly provisioning for the demo.

Creates a dedicated, clean demo project plus the three feature flags the app
uses, turns them on with sensible rollouts, and prints the SDK key to paste
into .env. Idempotent — safe to re-run.

Requires LD_API_KEY in .env (a LaunchDarkly API access token with writer access).
"""

import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://app.launchdarkly.com/api/v2"
API_KEY = os.environ.get("LD_API_KEY", "")
PROJECT_KEY = os.environ.get("LD_PROJECT_KEY", "nr-ld-demo")
ENV_KEY = os.environ.get("LD_ENVIRONMENT", "production")

if not API_KEY:
    sys.exit("LD_API_KEY is not set (fill in .env)")

JSON_HEADERS = {"Authorization": API_KEY, "Content-Type": "application/json"}
PATCH_HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json; domain-model=launchdarkly.semanticpatch",
}

FLAGS = [
    {
        "key": "new-checkout-flow",
        "name": "New Checkout Flow",
        "description": "Redesigned checkout experience. Adds latency vs. classic flow — visible in New Relic response times.",
        "rollout": {"true": 50, "false": 50},
    },
    {
        "key": "enable-recommendations",
        "name": "Enable Recommendations",
        "description": "Calls the external recommendations service — produces external/OTel spans in New Relic traces.",
        "rollout": {"true": 100, "false": 0},
    },
    {
        "key": "simulate-errors",
        "name": "Simulate Errors",
        "description": "Simulates payment provider timeouts during checkout for 25% of users — but only when they are in the new checkout flow. Gives a guarded release on new-checkout-flow a clean error-rate regression to detect.",
        "rollout": {"true": 25, "false": 75},
    },
]


def create_project():
    resp = requests.post(
        f"{API_BASE}/projects",
        headers=JSON_HEADERS,
        json={"name": "New Relic Demo", "key": PROJECT_KEY, "tags": ["demo", "new-relic"]},
        timeout=30,
    )
    if resp.status_code == 201:
        print(f"Created project '{PROJECT_KEY}'")
    elif resp.status_code == 409:
        print(f"Project '{PROJECT_KEY}' already exists")
    else:
        sys.exit(f"Failed to create project: {resp.status_code} {resp.text}")


def create_flag(flag):
    resp = requests.post(
        f"{API_BASE}/flags/{PROJECT_KEY}",
        headers=JSON_HEADERS,
        json={
            "name": flag["name"],
            "key": flag["key"],
            "description": flag["description"],
            "tags": ["nr-ld-demo"],
            "variations": [
                {"value": True, "name": "Enabled"},
                {"value": False, "name": "Disabled"},
            ],
            "defaults": {"onVariation": 0, "offVariation": 1},
            "clientSideAvailability": {"usingEnvironmentId": True, "usingMobileKey": False},
        },
        timeout=30,
    )
    if resp.status_code == 201:
        print(f"Created flag '{flag['key']}'")
    elif resp.status_code == 409:
        print(f"Flag '{flag['key']}' already exists")
    else:
        sys.exit(f"Failed to create flag '{flag['key']}': {resp.status_code} {resp.text}")


def configure_flag(flag):
    resp = requests.get(f"{API_BASE}/flags/{PROJECT_KEY}/{flag['key']}", headers=JSON_HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    var_ids = {str(v["value"]).lower(): v["_id"] for v in data["variations"]}

    instructions = [{"kind": "turnFlagOn"}]
    rollout = flag["rollout"]
    if rollout["true"] == 100:
        instructions.append({"kind": "updateFallthroughVariationOrRollout", "variationId": var_ids["true"]})
    else:
        instructions.append({
            "kind": "updateFallthroughVariationOrRollout",
            "rolloutContextKind": "user",
            "rolloutWeights": {
                var_ids["true"]: rollout["true"] * 1000,
                var_ids["false"]: rollout["false"] * 1000,
            },
        })

    resp = requests.patch(
        f"{API_BASE}/flags/{PROJECT_KEY}/{flag['key']}",
        headers=PATCH_HEADERS,
        json={"environmentKey": ENV_KEY, "instructions": instructions},
        timeout=30,
    )
    if resp.ok:
        desc = "100% on" if rollout["true"] == 100 else f"{rollout['true']}% rollout"
        print(f"Configured '{flag['key']}' in '{ENV_KEY}': on, {desc}")
    else:
        sys.exit(f"Failed to configure flag '{flag['key']}': {resp.status_code} {resp.text}")


def print_sdk_key():
    resp = requests.get(f"{API_BASE}/projects/{PROJECT_KEY}/environments/{ENV_KEY}", headers=JSON_HEADERS, timeout=30)
    resp.raise_for_status()
    sdk_key = resp.json()["apiKey"]
    print()
    print("Done. Paste this into .env:")
    print(f"LAUNCHDARKLY_SDK_KEY={sdk_key}")


if __name__ == "__main__":
    create_project()
    for f in FLAGS:
        create_flag(f)
        configure_flag(f)
    print_sdk_key()
