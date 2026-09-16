# Self-hosted database (replaces Supabase)

Postgres + PostgREST in Docker, bound to `127.0.0.1` only. Postgres itself
is never exposed — not to the host, not to the internet, only reachable
from the `postgrest` container over the compose network. PostgREST is the
only thing that's network-reachable, and only on localhost; your reverse
proxy puts it on the internet at `api.warescalation.com`, and cron scripts
on the same box call `http://127.0.0.1:3000` directly.

## 1. Restore

```
cd /opt/warescalation/selfhost   # or wherever this repo lives on the server
cp .env.example .env
```

Fill in `.env`:
- `POSTGRES_SUPERUSER_PASSWORD` — `openssl rand -base64 32`
- `AUTHENTICATOR_PASSWORD` — `openssl rand -hex 32` (**must** be hex, not base64: this
  value goes unescaped into a `postgres://user:pass@host` URI for PostgREST, and a
  base64 password can contain `/`, `+`, or `=`, which breaks the URI and makes
  PostgREST fail to connect with `PGRST002`)
- `PGRST_JWT_SECRET` — `openssl rand -base64 32` (must be ≥32 chars)

Put `backup.sql` at `../backup.sql` (or pass a path), then:

```
./setup.sh
```

This starts Postgres, creates the `anon`/`authenticated`/`service_role`/
`authenticator` roles (`service_role` gets `BYPASSRLS` — this is what lets
your backend write to tables that have RLS enabled with no policy, same as
Supabase's service key), restores the dump, drops the two `subscribers`
triggers that depended on Supabase-only extensions (`pg_net`, Vault), and
starts PostgREST.

## 2. Generate your new API keys

```
pip install pyjwt
PGRST_JWT_SECRET=$(grep PGRST_JWT_SECRET .env | cut -d= -f2) python3 gen_jwt.py
```

Prints `ANON_KEY=...` and `SERVICE_ROLE_KEY=...` — these replace
`sb_publishable_...` and `sb_secret_...` everywhere. Unlike Supabase's keys
they're self-issued, so keep `PGRST_JWT_SECRET` itself secret — anyone with
it can mint their own `service_role` token.

## 3. Verify

```
curl http://127.0.0.1:3000/oilprices?limit=1 \
  -H "apikey: $ANON_KEY" -H "Authorization: Bearer $ANON_KEY"
```

Should 200 with `[]` or rows if RLS/grants allow it for anon (most tables
won't — that's expected, only `subscribers` insert and the couple of
explicitly-public views are open to anon).

## 4. Reverse proxy

Pick whichever of `Caddyfile.snippet` / `nginx.conf.snippet` matches what's
already running on the box — check with `systemctl status caddy nginx` or
`ss -tlnp | grep -E ':80|:443'` before adding the other one, since two
proxies can't both bind :80/:443.

## 5. Point the code at the new host

Backend (`shipping.py`, `getoilprices.py`, `polymarket.py`, `xlsx_to_json.py`,
`shipmapping.py`, `regular_pulse.py`): swap `SUPABASE_URL`/`SUPABASE_KEY` +
`from supabase import create_client` for a `postgrest-py` client pointed at
`http://127.0.0.1:3000` with the `SERVICE_ROLE_KEY` — not yet done, ask
before making this pass since it touches 6 files.

Frontend (`index.html`, `alternative_data.html`, `msctraderoute.html`):
swap `SUPABASE_URL` → `https://api.warescalation.com`, `SUPABASE_KEY` →
`ANON_KEY`. `supabase-js` works fine against a self-hosted PostgREST this
way — not yet done.

## 6. Cron + DNS cutover

Once the code changes are verified locally against the new host:
- Move the scraping jobs (currently the 4 GitHub Actions workflows) to
  cron/systemd timers on this box, reading `.env` locally instead of GH
  Secrets, writing generated JSON straight into the web root instead of
  `git commit`/`push`.
- Disable the GitHub Actions schedule triggers (or delete the workflow
  files) once the server-side cron is confirmed working.
- Point `warescalation.com`'s DNS A/AAAA records at this box's IP, remove
  the GitHub Pages custom domain config.

Not yet done — flagging as the next step once 1-5 are confirmed working.
