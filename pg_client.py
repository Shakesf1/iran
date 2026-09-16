"""Shared PostgREST client for the self-hosted Postgres, replacing supabase-py.

Cron jobs run on the same box as the database, so this talks to PostgREST
over localhost directly rather than through the public api.warescalation.com
domain — no need to round-trip through Caddy/TLS for server-local writes.
"""
import os

from postgrest import SyncPostgrestClient


def get_client() -> SyncPostgrestClient:
    url = os.environ.get("POSTGREST_URL", "http://127.0.0.1:3000")
    key = os.environ["SERVICE_ROLE_KEY"]
    return SyncPostgrestClient(url, headers={"Authorization": f"Bearer {key}"})
