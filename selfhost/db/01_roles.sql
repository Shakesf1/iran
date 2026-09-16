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
    CREATE ROLE authenticator NOINHERIT LOGIN PASSWORD :'authpw';
  ELSE
    ALTER ROLE authenticator PASSWORD :'authpw';
  END IF;
END
$$;

GRANT anon TO authenticator;
GRANT authenticated TO authenticator;
GRANT service_role TO authenticator;
