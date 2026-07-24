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

# Persist the database and upstream account key on a volume.
VOLUME ["/app/data"]
ENV ACME_LAN_DATABASE_URL=sqlite+aiosqlite:////app/data/acme_lan.db \
    ACME_LAN_UPSTREAM_ACCOUNT_KEY_PATH=/app/data/upstream_account.key

EXPOSE 8000

CMD ["uvicorn", "acme_lan.main:app", "--host", "0.0.0.0", "--port", "8000"]
