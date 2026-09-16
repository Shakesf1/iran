-- Run AFTER restoring backup.sql.
--
-- subscribers had two triggers that called Supabase-only extensions
-- (net.http_post/net.http_delete from pg_net, vault.decrypted_secrets from
-- Supabase Vault) to sync new/removed subscribers to a Resend audience.
-- Neither extension exists on a plain Postgres install, and the dump's
-- `check_function_bodies = false` means restore succeeds silently — the
-- failure only shows up the first time someone actually subscribes, as a
-- failed INSERT. Drop them here; do the Resend sync in application code
-- instead (e.g. in regular_pulse.py, right after the insert succeeds).

DROP TRIGGER IF EXISTS "tr_sync_resend" ON "public"."subscribers";
DROP TRIGGER IF EXISTS "tr_delete_resend" ON "public"."subscribers";

DROP FUNCTION IF EXISTS "public"."sync_to_resend_clean"();
DROP FUNCTION IF EXISTS "public"."sync_insert_to_resend"();   -- dead code, no trigger ever called it
DROP FUNCTION IF EXISTS "public"."sync_delete_from_resend"();
