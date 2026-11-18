#!/usr/bin/env bash
# Restore an encrypted backup into an EMPTY database.
#
#   RESTORE_DATABASE_URL  postgres URL of the empty target database, connecting as the
#                         maintenance role (BYPASSRLS, member of clinicflow_owner) so
#                         ownership, grants, policies and triggers come back as they were.
#   BACKUP_PASSPHRASE     the passphrase used for the backup.
#
#   deploy/backup/restore.sh clinicflow-YYYYMMDD.dump.gpg
#
# Afterwards point the app at the restored database and run
# `python -m app.cli check-db-roles` and `alembic current` (see docs/DEPLOYMENT.md).
set -euo pipefail
in="${1:?usage: restore.sh BACKUP_FILE}"
: "${RESTORE_DATABASE_URL:?set RESTORE_DATABASE_URL}"
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"

gpg --batch --quiet --decrypt --passphrase-fd 3 "$in" 3< <(printf '%s' "$BACKUP_PASSPHRASE") \
  | pg_restore --exit-on-error --single-transaction --no-password --dbname="$RESTORE_DATABASE_URL"
echo "Restored $in."
