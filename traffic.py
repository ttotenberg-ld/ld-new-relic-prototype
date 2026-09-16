"""Continuous traffic generator for the demo storefront.

Hits the app's endpoints with a rotating cast of demo users at a gentle,
steady rate so both New Relic and LaunchDarkly always have fresh data.
Safe to leave running indefinitely; it retries quietly if the app restarts.
"""

import logging
import os
import random
import time
import uuid

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s traffic %(message)s")
logger = logging.getLogger("traffic")

BASE_URL = f"http://127.0.0.1:{os.environ.get('APP_PORT', '5050')}"

# (path, weight) — roughly what a small storefront's mix looks like
ENDPOINTS = [
    ("/", 20),
    ("/api/products", 35),
    ("/api/recommendations", 25),
    ("/checkout", 20),
]
PATHS = [e[0] for e in ENDPOINTS]
WEIGHTS = [e[1] for e in ENDPOINTS]


def main():
    logger.info("Generating traffic against %s (Ctrl+C to stop)", BASE_URL)
    while True:
        path = random.choices(PATHS, weights=WEIGHTS, k=1)[0]
        # Fresh UUID per request = unbounded unique-user population,
        # which guarded release analysis needs for sample size.
        user = f"user-{uuid.uuid4().hex[:12]}"
        try:
            resp = requests.get(f"{BASE_URL}{path}", params={"user": user}, timeout=15)
            logger.info("%s %s user=%s -> %s", "GET", path, user, resp.status_code)
        except requests.RequestException as exc:
            logger.warning("app unreachable (%s), retrying shortly", exc.__class__.__name__)
            time.sleep(5)
            continue
        time.sleep(random.uniform(0.8, 2.5))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
