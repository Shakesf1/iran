#!/usr/bin/env python3
"""Send a failure email via the Resend API (no local MTA needed — most
cloud providers, Hetzner included, block outbound port 25 by default, so
plain sendmail/mail usually can't deliver anyway).

Usage: alert.py <job_name> < captured-output
"""
import os
import sys

import requests

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
ALERT_FROM_EMAIL = os.environ.get("ALERT_FROM_EMAIL", "alerts@warescalation.com")
ALERT_TO_EMAIL = os.environ.get("ALERT_TO_EMAIL", "sverhoeven@gmail.com")

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: alert.py <job_name> < captured-output")
    job_name = sys.argv[1]
    output = sys.stdin.read()[-20000:]  # Resend has a body size limit; tail is most useful anyway

    if not RESEND_API_KEY:
        print(f"[alert.py] RESEND_API_KEY not set, cannot send alert for {job_name}", file=sys.stderr)
        print(output, file=sys.stderr)
        return

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
        json={
            "from": ALERT_FROM_EMAIL,
            "to": [ALERT_TO_EMAIL],
            "subject": f"[warescalation cron] {job_name} failed",
            "text": output or "(no output captured)",
        },
        timeout=15,
    )
    if resp.status_code >= 300:
        print(f"[alert.py] Resend API error {resp.status_code}: {resp.text}", file=sys.stderr)

if __name__ == "__main__":
    main()
