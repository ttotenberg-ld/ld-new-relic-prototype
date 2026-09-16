#!/usr/bin/env bash
# Start the demo: Flask app under the New Relic agent + continuous traffic generator.
# Leave it running as long as you like; Ctrl+C stops everything.
set -euo pipefail
cd "$(dirname "$0")"

# Load .env
set -a
source .env
set +a

if [[ -z "${NEW_RELIC_LICENSE_KEY:-}" || -z "${LAUNCHDARKLY_SDK_KEY:-}" ]]; then
  echo "Fill in NEW_RELIC_LICENSE_KEY and LAUNCHDARKLY_SDK_KEY in .env first." >&2
  echo "(Run 'python setup_launchdarkly.py' with LD_API_KEY set to provision the LD project and get the SDK key.)" >&2
  exit 1
fi

# Bootstrap venv on first run
if [[ ! -d .venv ]]; then
  echo "Creating virtualenv and installing dependencies (first run only)..."
  python3 -m venv .venv
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt
fi

# Overlay our fixed copy of the agent's LaunchDarkly hook (the
# darkly-nr-integration branch has NameError bugs that prevent flag data
# from attaching to spans — see patches/observability_ldclient.py).
cp patches/observability_ldclient.py \
  "$(./.venv/bin/python -c 'import newrelic.hooks, os; print(os.path.dirname(newrelic.hooks.__file__))')/observability_ldclient.py"

export NEW_RELIC_CONFIG_FILE=newrelic.ini
APP_PORT="${APP_PORT:-5050}"

cleanup() {
  echo "Shutting down..."
  kill "${TRAFFIC_PID:-}" "${APP_PID:-}" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "Starting app on port ${APP_PORT} (New Relic app name: ${NEW_RELIC_APP_NAME:-LaunchDarkly NR Demo})"
./.venv/bin/newrelic-admin run-program ./.venv/bin/python app.py &
APP_PID=$!

# Wait for the app to come up before generating traffic
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "App failed to start — see output above / newrelic-agent.log" >&2
    exit 1
  fi
  sleep 1
done

echo "App is up — starting traffic generator"
./.venv/bin/python traffic.py &
TRAFFIC_PID=$!

wait "$APP_PID"
