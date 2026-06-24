-- Runs once on first Postgres init (as the superuser), before any migration.
-- Creates the restricted role the app serves requests as (M0.2 two-role split,
-- DECISIONS.md 2026-06-24): NOSUPERUSER + NOBYPASSRLS so Postgres RLS is actually
-- enforced. DDL/migrations run as the owner (POSTGRES_USER); this role only ever
-- gets the table GRANTs handed out by the Alembic migration. Roles are
-- cluster-global, so this also applies to the `tolera_test` database.
--
-- Local-dev credential ONLY (mirrors the committed `tolera:tolera`); production
-- provisions the role + a real password out of band (Kamal secret → APP_DATABASE_URL).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tolera_app') THEN
        CREATE ROLE tolera_app LOGIN PASSWORD 'tolera_app' NOSUPERUSER NOBYPASSRLS;
    END IF;
END
$$;
