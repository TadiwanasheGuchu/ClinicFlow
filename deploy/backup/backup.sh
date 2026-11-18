#!/usr/bin/env bash
# Encrypted logical backup of the ClinicFlow database.
#
#   BACKUP_DATABASE_URL  postgres URL for the maintenance role (BYPASSRLS, member of
#                        clinicflow_owner). RLS is forced for every other role, so a dump
#                        as any other role would fail - which is the point.
#   BACKUP_PASSPHRASE    long random passphrase; keep a copy outside GitHub too.
#
#   deploy/backup/backup.sh clinicflow-YYYYMMDD.dump.gpg
set -euo pipefail
out="${1:?usage: backup.sh OUTPUT_FILE}"
: "${BACKUP_DATABASE_URL:?set BACKUP_DATABASE_URL}"
: "${BACKUP_PASSPHRASE:?set BACKUP_PASSPHRASE}"

pg_dump --format=custom --no-password --dbname="$BACKUP_DATABASE_URL" \
  | gpg --batch --yes --quiet --symmetric --cipher-algo AES256 \
        --passphrase-fd 3 --output "$out" 3< <(printf '%s' "$BACKUP_PASSPHRASE")

# Prove the file decrypts and is a complete archive before calling it a backup.
entries=$(gpg --batch --quiet --decrypt --passphrase-fd 3 "$out" 3< <(printf '%s' "$BACKUP_PASSPHRASE") \
  | pg_restore --list | grep -c "TABLE DATA" || true)
if [ "$entries" -lt 10 ]; then
  echo "Backup looks incomplete ($entries tables)." >&2
  exit 1
fi
echo "Backup written to $out ($(du -h "$out" | cut -f1), $entries tables)."
