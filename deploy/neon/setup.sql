-- One-time database setup on Neon (run in the Neon SQL Editor, connected to the default
-- "neondb" database as the project's default role). See docs/DEPLOYMENT.md, step 1.
--
-- Replace the three passwords first. Use long random letters and digits only (no symbols,
-- so they can go into connection URLs unchanged), e.g. from a password manager or
-- `openssl rand -hex 24`. Keep them in your password manager.
--
-- Roles:
--   clinicflow_owner        owns the schema and runs migrations; row-level security applies
--   clinicflow_app          used by the running app; row-level security applies
--   clinicflow_maintenance  backups only; bypasses row-level security (never give it to the app)
-- Roles made in Neon's web console get extra privileges, so create these with SQL.

CREATE ROLE clinicflow_owner LOGIN NOBYPASSRLS PASSWORD 'REPLACE_WITH_OWNER_PASSWORD';
CREATE ROLE clinicflow_app LOGIN NOBYPASSRLS PASSWORD 'REPLACE_WITH_APP_PASSWORD';
CREATE ROLE clinicflow_maintenance LOGIN BYPASSRLS PASSWORD 'REPLACE_WITH_MAINTENANCE_PASSWORD';
GRANT clinicflow_owner TO clinicflow_maintenance;
-- Lets the default role create a database owned by clinicflow_owner.
GRANT clinicflow_owner TO CURRENT_USER;

CREATE DATABASE clinicflow OWNER clinicflow_owner;

-- Then switch the SQL Editor to the new "clinicflow" database and run:
--   REVOKE ALL ON SCHEMA public FROM PUBLIC;
--   ALTER SCHEMA public OWNER TO clinicflow_owner;
-- The app creates all tables itself on first start.
