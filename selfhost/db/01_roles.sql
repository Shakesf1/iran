-- Recreates the PostgREST role model that Supabase's platform normally sets
-- up for you. Run this BEFORE restoring backup.sql, since the dump's GRANT
-- and CREATE POLICY statements reference these role names.
--
-- Invoke with: psql -v authpw="$AUTHENTICATOR_PASSWORD" -f 01_roles.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOINHERIT;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOINHERIT;
  END IF;

  -- BYPASSRLS is the load-bearing part: this is what lets your backend
  -- scripts (using the service_role JWT) read/write tables that have RLS
  -- enabled with no permissive policy, same as Supabase's service_role.
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
  END IF;

  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
    CREATE ROLE authenticator NOINHERIT LOGIN;
  END IF;

  -- Dummy role: the dump has a few ALTER DEFAULT PRIVILEGES FOR ROLE
  -- "supabase_admin" statements left over from the source project. It
  -- never needs to log in here, it just needs to exist so those statements
  -- don't error.
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin NOLOGIN;
  END IF;
END
$$;

-- psql's :'var' substitution doesn't reach inside a DO $$ ... $$ body (it's
-- sent to the server as one opaque dollar-quoted string), so the password
-- has to be set here, as a plain top-level statement, instead of inside
-- the block above.
ALTER ROLE authenticator PASSWORD :'authpw';

GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;
