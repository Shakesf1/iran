#!/usr/bin/env bash
# Wraps a cron command: prevents overlapping runs of the same job, adds
# optional jitter (to avoid fixed-interval scraping detection, matching
# what the old GitHub Actions workflows did), captures output, and emails
# a failure alert via Resend on non-zero exit.
#
# Usage: run_job.sh <job_name> <max_jitter_seconds> <command...>
set -uo pipefail

JOB_NAME="$1"
MAX_JITTER="$2"
shift 2

cd "$(dirname "$0")/../.."   # repo root
set -a; source .env; set +a
ALERT_PY=".venv/bin/python3"

if [ "$MAX_JITTER" -gt 0 ]; then
  sleep "$((RANDOM % MAX_JITTER))"
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
