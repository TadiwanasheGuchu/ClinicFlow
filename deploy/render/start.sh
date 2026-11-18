#!/usr/bin/env bash
# Starts the API (internal only) and the web app in one container. If either exits, the
# container exits and the host restarts it.
set -euo pipefail
# If either process exits, stop the other too, so the host sees one failure and restarts.
trap 'kill 0' EXIT

BACKEND_DIR="${BACKEND_DIR:-/app/backend}"
WEB_DIR="${WEB_DIR:-/app/web}"

cd "$BACKEND_DIR"
python -m app.cli check-db-roles      # refuse to run with a role that can bypass RLS
alembic upgrade head
python -m app.cli sync-permissions

# The API is not exposed: only the web app (server-side) talks to it.
uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-server-header &

cd "$WEB_DIR"
export CLINICFLOW_API_URL="http://127.0.0.1:8000"
# Keep within a 512 MB instance alongside the API.
export NODE_OPTIONS="--max-old-space-size=256"
PORT="${PORT:-10000}" HOSTNAME=0.0.0.0 node server.js &

wait -n
exit $?
