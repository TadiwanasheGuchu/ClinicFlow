#!/bin/sh
# Apply migrations and synchronise the permission catalogue, then start the API.
set -e
alembic upgrade head
python -m app.cli sync-permissions
exec "$@"
