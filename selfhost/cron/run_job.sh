#!/usr/bin/env bash
# Wraps a cron command: prevents overlapping runs of the same job, adds
# optional jitter (to avoid fixed-interval scraping detection, matching
# what the old GitHub Actions workflows did), optionally ensures a Chrome
# virtual display is up, captures output, and emails a failure alert via
# Resend on non-zero exit.
#
# Usage: run_job.sh <job_name> <max_jitter_seconds> <needs_display:0|1> <command...>
set -uo pipefail

JOB_NAME="$1"
MAX_JITTER="$2"
NEEDS_DISPLAY="$3"
shift 3

cd "$(dirname "$0")/../.."   # repo root
set -a; source .env; set +a
ALERT_PY=".venv/bin/python3"

if [ "$MAX_JITTER" -gt 0 ]; then
  sleep "$((RANDOM % MAX_JITTER))"
fi

if [ "$NEEDS_DISPLAY" = "1" ]; then
  # Clear out any crashed/leftover Chrome from a prior run of THIS job
  # before it grabs the lock below — safe because shipping and shipmapping
  # only ever run sequentially (chained with && in the crontab), never
  # concurrently with each other.
  pkill -9 -f "chrome.*chrome_profile_" 2>/dev/null || true
  rm -rf /tmp/.com.google.Chrome.* 2>/dev/null || true
  if ! pgrep -f "Xvfb :99" > /dev/null; then
    Xvfb :99 -screen 0 1920x1080x24 &
    disown
    sleep 2
  fi
  export DISPLAY=:99
fi

LOCK_FILE="/tmp/warescalation_cron_${JOB_NAME}.lock"
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
  echo "[$(date -u +%FT%TZ)] $JOB_NAME already running, skipping this tick" \
    | "$ALERT_PY" selfhost/cron/alert.py "$JOB_NAME (overlap)"
  exit 0
fi

OUTPUT=$("$@" 2>&1)
STATUS=$?

if [ $STATUS -ne 0 ]; then
  echo "$OUTPUT" | tail -c 20000 | "$ALERT_PY" selfhost/cron/alert.py "$JOB_NAME"
fi

echo "$OUTPUT"
exit $STATUS
