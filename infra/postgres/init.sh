#!/bin/bash
# Creates the ClinicFlow database roles on first container start.
#   clinicflow_owner — owns the schema; runs migrations. Not a superuser, so
#                      FORCE ROW LEVEL SECURITY applies to it too.
#   clinicflow_app   — used by the API at runtime. Cannot bypass RLS.
#   keycloak         — separate database for the identity provider.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-SQL
  CREATE ROLE clinicflow_owner LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${CLINICFLOW_OWNER_PASSWORD}';
  CREATE ROLE clinicflow_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${CLINICFLOW_APP_PASSWORD}';
  CREATE DATABASE clinicflow OWNER clinicflow_owner;
  CREATE ROLE keycloak LOGIN PASSWORD '${KEYCLOAK_DB_PASSWORD}';
  CREATE DATABASE keycloak OWNER keycloak;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname clinicflow <<-SQL
  ALTER SCHEMA public OWNER TO clinicflow_owner;
  REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
