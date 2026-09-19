# syntax=docker/dockerfile:1
FROM node:22.20-bookworm-slim AS frontend
WORKDIR /build/frontend
RUN corepack enable && corepack prepare pnpm@10.20.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts
COPY frontend/ ./
RUN pnpm build

FROM ghcr.io/astral-sh/uv:0.12.8 AS uv
FROM python:3.11-slim-bookworm AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

FROM python:3.11-slim-bookworm AS runtime
LABEL org.opencontainers.image.title="tiktok-live-monitor"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/backend/.venv/bin:$PATH" \
    STATIC_DIR=/app/frontend/build HOST=0.0.0.0 PORT=8000
RUN groupadd --gid 10001 monitor && useradd --uid 10001 --gid monitor --no-create-home monitor
WORKDIR /app/backend
COPY --from=dependencies /app/backend/.venv ./.venv
COPY backend/app ./app
COPY --from=frontend /build/frontend/build /app/frontend/build
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "app"]
