"""Demo storefront service instrumented with New Relic + LaunchDarkly.

Based on the New Relic team's prototype (newrelic-launchdarkly-proto): the
custom `darkly-nr-integration` agent branch attaches LaunchDarkly flag data
to New Relic spans, and the LaunchDarkly observability plugin sends the same
telemetry to LaunchDarkly.

Run via: newrelic-admin run-program python app.py  (see run.sh)
"""

import http.client
import logging
import os
import random
import time
import uuid
import zlib

from dotenv import load_dotenv

load_dotenv()

import newrelic.agent
import requests
from flask import Flask, jsonify, request

import ldclient
from ldclient import Context
from ldclient.config import Config
from ldobserve import ObservabilityConfig, ObservabilityPlugin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("demo-storefront")

app = Flask(__name__)

FLAG_NEW_CHECKOUT = "new-checkout-flow"
FLAG_RECOMMENDATIONS = "enable-recommendations"
FLAG_SIMULATE_ERRORS = "simulate-errors"

sdk_key = os.environ.get("LAUNCHDARKLY_SDK_KEY") or os.environ.get("DARKLY_SDK_KEY")
if not sdk_key:
    raise SystemExit("LAUNCHDARKLY_SDK_KEY is not set (fill in .env)")

observability_config = ObservabilityConfig(
    service_name="nr-ld-demo-storefront",
    service_version="1.0.0",
)
plugin = ObservabilityPlugin(observability_config)
ldclient.set_config(Config(sdk_key, plugins=[plugin]))

if not ldclient.get().is_initialized():
    raise SystemExit("LaunchDarkly SDK failed to initialize — check LAUNCHDARKLY_SDK_KEY")

ldclient.get().flush()
logger.info("LaunchDarkly SDK initialized")

# Each visitor gets a unique UUID-based key (an effectively infinite
# population, which guarded releases need for sample size), with persona
# attributes derived deterministically from the key so a returning key
# always looks like the same person.
FIRST_NAMES = ["Sandy", "Alex", "Jordan", "Sam", "Casey", "Morgan", "Riley", "Taylor", "Devon", "Quinn"]
LAST_NAMES = ["Smith", "Rivera", "Lee", "Patel", "Nguyen", "Chen", "Brooks", "Kim", "Garcia", "Murphy"]
PLANS = ["free", "pro", "enterprise"]
REGIONS = ["us-east", "us-west", "eu-west", "eu-central", "ap-south"]


def current_context() -> Context:
    key = request.args.get("user") or f"user-{uuid.uuid4().hex[:12]}"
    seed = zlib.crc32(key.encode())
    first = FIRST_NAMES[seed % 10]
    last = LAST_NAMES[(seed // 10) % 10]
    plan = PLANS[seed % 3]
    region = REGIONS[seed % 5]
    newrelic.agent.add_custom_attribute("enduser.id", key)
    newrelic.agent.add_custom_attribute("plan", plan)
    return (
        Context.builder(key)
        .name(f"{first} {last}")
        .set("firstName", first)
        .set("lastName", last)
        .set("email", f"{key}@example.com")
        .set("plan", plan)
        .set("region", region)
        .build()
    )


@app.route("/")
def home():
    context = current_context()
    new_checkout = ldclient.get().variation(FLAG_NEW_CHECKOUT, context, False)
    logger.info("Home page rendered (checkout variant: %s)", "new" if new_checkout else "classic")
    return jsonify({"page": "home", "checkout_variant": "new" if new_checkout else "classic"})


@app.route("/api/products")
def products():
    current_context()
    time.sleep(random.uniform(0.02, 0.08))
    return jsonify({
        "products": [
            {"id": 1, "name": "Toggle Tee", "price": 24.00},
            {"id": 2, "name": "Dark Launch Hoodie", "price": 58.00},
            {"id": 3, "name": "Kill Switch Cap", "price": 19.00},
        ]
    })


@app.route("/api/recommendations")
def recommendations():
    context = current_context()
    enabled = ldclient.get().variation(FLAG_RECOMMENDATIONS, context, False)
    if enabled:
        # Simulated call to an external recommendations service.
        # requests -> New Relic instrumented; http.client -> OTel instrumented
        # (mirrors the NR prototype so both span types appear in traces).
        requests.get("http://example.com", timeout=10)
        conn = http.client.HTTPConnection("example.com")
        conn.request("GET", "/recommendations", headers={"Host": "example.com"})
        conn.getresponse().read()
        conn.close()
        logger.info("Recommendations served from external service for %s", context.key)
        return jsonify({"recommendations": [2, 3], "source": "recommendation-service"})
    logger.info("Recommendations flag off for %s, serving static list", context.key)
    return jsonify({"recommendations": [1], "source": "static"})


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    context = current_context()
    new_flow = ldclient.get().variation(FLAG_NEW_CHECKOUT, context, False)
    simulate_errors = ldclient.get().variation(FLAG_SIMULATE_ERRORS, context, False)

    # Errors only occur in the new checkout flow, so a guarded release on
    # new-checkout-flow sees a clean error-rate regression and rolls back.
    if new_flow and simulate_errors and random.random() < 0.6:
        logger.error("Payment provider timeout during checkout for %s", context.key)
        raise RuntimeError("Payment provider timed out (simulated via 'simulate-errors' flag)")

    if new_flow:
        time.sleep(random.uniform(0.15, 0.40))  # redesigned flow is heavier
        variant = "new"
    else:
        time.sleep(random.uniform(0.04, 0.12))
        variant = "classic"

    order_id = f"ord-{random.randint(10000, 99999)}"
    logger.info("Checkout completed for %s via %s flow (%s)", context.key, variant, order_id)
    return jsonify({"status": "complete", "order_id": order_id, "flow": variant})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", "5050"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
