# acme-lan container image. The Vue dashboard is pre-built and committed under
# src/acme_lan/web/dist, so no Node toolchain is needed at build time.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The cisco_ios deploy plugin talks to legacy network gear through the system ssh client:
# paramiko 5 removed ssh-rsa and the SHA-1 key exchanges outright, and old IOS offers
# nothing else. OpenSSH still supports them when re-enabled per connection.
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Migrations live at the repo root; ship them so the entrypoint can auto-migrate.
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# Persist the database and secrets on a volume.
VOLUME ["/app/data"]
# NOTE: settings named here are set in the environment, so they are *enforced* — the
# dashboard shows them read-only. Keep this list to things that must track the image layout.
ENV ACME_LAN_DATABASE_URL=sqlite+aiosqlite:////app/data/acme_lan.db \
    ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH=/app/data/upstream_account.key \
    ACME_LAN_MIGRATIONS_DIR=/app/migrations \
    ACME_LAN_CONFIG_FILE=/app/data/config.yml

EXPOSE 8000

# The `acme-lan` entrypoint runs schema + data migrations, then serves (HTTPS if a
# service cert is configured).
CMD ["acme-lan"]
