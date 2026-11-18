#!/bin/sh
# Check the database roles can't bypass RLS, apply migrations and synchronise the
# permission catalogue, then start the API.
set -e
python -m app.cli check-db-roles
alembic upgrade head
python -m app.cli sync-permissions
exec "$@"
