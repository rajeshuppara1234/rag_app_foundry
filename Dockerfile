# syntax=docker/dockerfile:1
FROM node:24-bookworm-slim AS web
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY web/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS dependencies
RUN pip install --no-cache-dir uv==0.11.26
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PATH="/app/.venv/bin:$PATH" APP_ENV=production
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY --from=dependencies /app/.venv /app/.venv
COPY app/ ./app/
COPY --from=web /build/app/static ./app/static/
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--no-server-header", "--timeout-graceful-shutdown", "230"]
