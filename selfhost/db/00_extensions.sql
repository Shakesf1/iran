-- The postgis/postgis Docker image auto-installs a full extension bundle
-- (postgis, postgis_topology, fuzzystrmatch, postgis_tiger_geocoder) into
-- the public schema on first boot. All of them end up depending on that
-- schema, which blocks backup.sql's `DROP SCHEMA IF EXISTS "public"`
-- during restore. Drop the whole bundle here — setup.sh re-installs just
-- postgis (the only one get_bab_el_mandeb_transits_new() actually needs)
-- right after the dump recreates the schema, by injecting a statement
-- into the restore stream.
DROP EXTENSION IF EXISTS postgis_tiger_geocoder, postgis_topology, postgis, fuzzystrmatch CASCADE;
