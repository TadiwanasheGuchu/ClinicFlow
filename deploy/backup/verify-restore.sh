#!/usr/bin/env bash
# Restore drill: restore an encrypted backup into a scratch PostgreSQL server and check it.
# Proves the backup can actually be restored, by a non-superuser role, with row-level
# security, triggers and the migration history intact.
#
#   SCRATCH_ADMIN_URL   superuser URL of a throwaway server (e.g. a CI service container)
#   BACKUP_PASSPHRASE   the backup passphrase
#   SOURCE_COUNTS       optional file of "table count" lines to compare against
#
#   deploy/backup/verify-restore.sh clinicflow-YYYYMMDD.dump.gpg
set -euo pipefail
file="${1:?usage: verify-restore.sh BACKUP_FILE}"
: "${SCRATCH_ADMIN_URL:?set SCRATCH_ADMIN_URL}"
here="$(cd "$(dirname "$0")" && pwd)"
host_part="${SCRATCH_ADMIN_URL#*@}"; host_part="${host_part%%/*}"
pw="drill-$RANDOM$RANDOM"

# Safety: only ever run against a throwaway server. It (re)creates roles and sets their
# passwords, so refuse a server that holds a real ClinicFlow database.
if [ "$(psql "$SCRATCH_ADMIN_URL" -tAc "SELECT count(*) FROM pg_database WHERE datname = 'clinicflow'")" != "0" ]; then
  echo "This server has a 'clinicflow' database; use a throwaway server for the drill." >&2
  exit 2
fi

psql "$SCRATCH_ADMIN_URL" -v ON_ERROR_STOP=1 -q <<SQL
DROP DATABASE IF EXISTS clinicflow_drill;
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clinicflow_owner') THEN CREATE ROLE clinicflow_owner LOGIN NOBYPASSRLS; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clinicflow_app') THEN CREATE ROLE clinicflow_app LOGIN NOBYPASSRLS; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'clinicflow_maintenance') THEN CREATE ROLE clinicflow_maintenance LOGIN BYPASSRLS; END IF;
END \$\$;
ALTER ROLE clinicflow_owner PASSWORD '$pw';
ALTER ROLE clinicflow_app PASSWORD '$pw';
ALTER ROLE clinicflow_maintenance PASSWORD '$pw';
GRANT clinicflow_owner TO clinicflow_maintenance;
CREATE DATABASE clinicflow_drill OWNER clinicflow_owner;
SQL
psql "${SCRATCH_ADMIN_URL%/*}/clinicflow_drill" -v ON_ERROR_STOP=1 -q \
  -c "REVOKE ALL ON SCHEMA public FROM PUBLIC" -c "ALTER SCHEMA public OWNER TO clinicflow_owner"

RESTORE_DATABASE_URL="postgresql://clinicflow_maintenance:$pw@$host_part/clinicflow_drill" "$here/restore.sh" "$file"

maint="postgresql://clinicflow_maintenance:$pw@$host_part/clinicflow_drill"
app="postgresql://clinicflow_app:$pw@$host_part/clinicflow_drill"
# 1. Row-level security still hides everything from the app role without a tenant.
hidden=$(psql "$app" -tAc "SELECT count(*) FROM patients")
[ "$hidden" = "0" ] || { echo "RLS check failed: app role sees $hidden patients" >&2; exit 1; }
# 2. Integrity triggers came back (the audit log refuses deletes).
if psql "$maint" -qc "DELETE FROM audit_logs" 2>/dev/null; then echo "Audit log trigger missing" >&2; exit 1; fi
# 3. Same migration revision as the code being deployed.
(cd "$here/../../backend" && CLINICFLOW_MIGRATION_DATABASE_URL="postgresql+psycopg://clinicflow_owner:$pw@$host_part/clinicflow_drill" \
  uv run -q alembic current 2>/dev/null | tee /dev/stderr | grep -q "(head)") || { echo "Migration revision is not head" >&2; exit 1; }
# 4. Row counts match the source, when given.
psql "$maint" -tAc "SELECT format('%s %s', c.relname, (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %I', c.relname), false, true, '')))[1]::text)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1" > /tmp/drill-counts.txt
if [ -n "${SOURCE_COUNTS:-}" ]; then
  diff "$SOURCE_COUNTS" /tmp/drill-counts.txt >&2 || { echo "Row counts differ from the source" >&2; exit 1; }
fi
echo "Restore drill passed: $(wc -l < /tmp/drill-counts.txt) tables, RLS and triggers intact, schema at head."
