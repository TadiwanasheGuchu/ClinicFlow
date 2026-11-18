#!/usr/bin/env bash
# Print "table rowcount" for every table (maintenance role, which bypasses RLS).
#   BACKUP_DATABASE_URL=... deploy/backup/counts.sh > counts.txt
set -euo pipefail
psql "${BACKUP_DATABASE_URL:?}" -tAc "SELECT format('%s %s', c.relname, (xpath('/row/n/text()', query_to_xml(format('select count(*) as n from %I', c.relname), false, true, '')))[1]::text)
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1"
