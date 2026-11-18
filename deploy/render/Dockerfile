# Single-container image for hosts that give one web service (e.g. Render's free tier):
# the Next.js web app is public on $PORT; the API and the notification worker run inside
# the same container and are reachable only from it (127.0.0.1:8000).
# Build context: repository root.

FROM node:22.12-bookworm-slim AS web
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS run
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv \
    NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./

WORKDIR /app/web
COPY --from=web /web/.next/standalone ./
COPY --from=web /web/.next/static ./.next/static

COPY deploy/render/start.sh /app/start.sh
RUN useradd --system --uid 10001 clinicflow && chmod +x /app/start.sh /app/backend/scripts/entrypoint.sh
USER clinicflow
EXPOSE 10000
CMD ["/app/start.sh"]
