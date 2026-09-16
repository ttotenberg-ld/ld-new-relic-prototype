# LaunchDarkly ↔ New Relic Demo

A small, self-contained demo storefront that continuously streams data to **both**
New Relic and LaunchDarkly. Built on the New Relic team's
[newrelic-launchdarkly-proto](https://github.com/hmstepanek/newrelic-launchdarkly-proto),
which uses a custom New Relic Python agent branch (`darkly-nr-integration`) that
attaches LaunchDarkly feature flag data to New Relic spans/traces, plus the
LaunchDarkly observability plugin so the same telemetry lands in LaunchDarkly.

Designed to be left running indefinitely on a laptop: a traffic generator hits
the app every second or two, each request as a brand-new UUID-keyed visitor
(an unbounded user population, which guarded releases need for sample size),
so both platforms always show a steady trickle of fresh, exclusively-demo data.

## What you'll see

**In New Relic** (APM entity `LaunchDarkly NR Demo`):
- Web transactions for `/`, `/api/products`, `/api/recommendations`, `/checkout`
- Distributed traces with feature flag data attached to spans (via the custom agent branch)
- External + OTel spans to the "recommendations service" when `enable-recommendations` is on
- A low, steady error rate on `/checkout` driven by the `simulate-errors` flag
- Forwarded application logs, decorated with trace metadata

**In LaunchDarkly** (project `nr-ld-demo`):
- Live flag evaluations / insights for the three demo flags
- Observability data (traces, logs) from the LaunchDarkly observability plugin

## The flags

| Flag | Rollout | Effect |
|---|---|---|
| `new-checkout-flow` | 50% of users | Redesigned checkout with higher latency — visible in NR response times |
| `enable-recommendations` | 100% on | Calls an external service — produces external/OTel spans in traces |
| `simulate-errors` | 25% of users | Simulated payment timeouts on `/checkout`, **only in the new checkout flow** — gives a guarded release on `new-checkout-flow` a clean error-rate regression to detect and roll back |

## Setup

1. **Fill in `.env`** with your New Relic ingest license key and a LaunchDarkly
   API access token (`LD_API_KEY`).

2. **Provision LaunchDarkly** (one time). Creates a clean `nr-ld-demo` project,
   the three flags, and turns them on with rollouts; prints the SDK key:
   ```
   python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
   ./.venv/bin/python setup_launchdarkly.py
   ```
   Paste the printed `LAUNCHDARKLY_SDK_KEY` into `.env`.

3. **Run the demo**:
   ```
   ./run.sh
   ```
   This starts the app under `newrelic-admin` and the traffic generator.
   Ctrl+C stops both. Leave it running as long as you like.

## Files

- `app.py` — Flask storefront, LD SDK + observability plugin, flag-driven behavior
- `traffic.py` — steady background traffic (~25–45 req/min), unique UUID visitor per request
- `setup_launchdarkly.py` — idempotent LD project/flag provisioning
- `newrelic.ini` — agent config (spans, distributed tracing, OTel bridge, log forwarding)
- `run.sh` — one-command bootstrap + run
- `.env` — all keys/config (gitignored; copy `.env.example` to start)

## Notes

- Port defaults to **5050** (macOS AirPlay squats on 5000); change `APP_PORT` in `.env` if needed.
- The New Relic agent comes from the prototype's `darkly-nr-integration` branch via
  `requirements.txt`. If that branch ever disappears, swap the git line for `newrelic`
  on PyPI — everything still works minus flag data on spans.
- Toggling flags in the LaunchDarkly UI while the demo runs changes app behavior
  live (latency, errors, external calls) — that's the demo story: flip a flag,
  watch New Relic react.
