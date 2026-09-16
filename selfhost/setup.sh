#!/usr/bin/env bash
# Brings up Postgres + PostgREST and restores backup.sql into it.
# Run from inside selfhost/, with .env already filled in and backup.sql
# placed one level up (../backup.sql) or pass its path as $1.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "Missing .env — copy .env.example to .env and fill in secrets first." >&2
  exit 1
fi
set -a
source .env
set +a

BACKUP_FILE="${1:-../backup.sql}"
if [ ! -f "$BACKUP_FILE" ]; then
  echo "backup.sql not found at $BACKUP_FILE" >&2
  exit 1
fi

echo "==> Starting Postgres"
docker compose up -d db
echo "==> Waiting for Postgres to be healthy"
until [ "$(docker inspect -f '{{.State.Health.Status}}' warescalation_db 2>/dev/null)" = "healthy" ]; do
  sleep 2
done

echo "==> Dropping the postgis image's bundled extensions (they'd block backup.sql's DROP SCHEMA public)"
docker compose exec -T db psql -U postgres -d postgres -f - < db/00_extensions.sql

echo "==> Creating anon/authenticated/service_role/authenticator roles"
docker compose exec -T db psql -U postgres -d postgres -v authpw="$AUTHENTICATOR_PASSWORD" -f - < db/01_roles.sql

echo "==> Restoring backup.sql (this is a ~700MB dump, will take a while)"
# \restrict/\unrestrict are psql-18+-only guard commands that pg_dump 18.1
# wraps its output in; the postgis image's bundled psql (17.x) doesn't
# recognize them. Safe to strip since we trust this dump. Also re-install
# postgis immediately after the dump recreates the public schema (dropped
# above), so it's back in place before anything needs it further down
# (e.g. the spatial_ref_sys COPY, ST_* function bodies).
grep -v -E '^\\(restrict|unrestrict) ' "$BACKUP_FILE" \
  | sed '/^CREATE SCHEMA "public";$/a CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA "public";' \
  | docker compose exec -T db psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f -

echo "==> Patching out the pg_net/vault-dependent resend triggers"
docker compose exec -T db psql -U postgres -d postgres -f - < db/02_patch_resend_triggers.sql

echo "==> Starting PostgREST"
docker compose up -d postgrest

echo "==> Done. PostgREST listening on 127.0.0.1:3000"
echo "==> Generate your anon/service_role keys with:"
echo "    PGRST_JWT_SECRET=\$PGRST_JWT_SECRET python3 gen_jwt.py"
