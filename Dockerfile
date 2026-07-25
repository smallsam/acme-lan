# acme-lan container image. The Vue dashboard is pre-built and committed under
# src/acme_lan/web/dist, so no Node toolchain is needed at build time.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Migrations live at the repo root; ship them so the entrypoint can auto-migrate.
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# Persist the database and secrets on a volume.
VOLUME ["/app/data"]
ENV ACME_LAN_DATABASE_URL=sqlite+aiosqlite:////app/data/acme_lan.db \
    ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH=/app/data/upstream_account.key \
    ACME_LAN_MIGRATIONS_DIR=/app/migrations

EXPOSE 8000

# The `acme-lan` entrypoint runs schema + data migrations, then serves (HTTPS if a
# service cert is configured).
CMD ["acme-lan"]
