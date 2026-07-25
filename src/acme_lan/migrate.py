"""Automatic database migrations, run on startup so new releases self-upgrade.

Schema changes are Alembic migrations under ``migrations/versions``; data migrations
(transforming existing rows, e.g. re-encrypting secrets) are idempotent steps in
``migrations/data.py``. The container entrypoint runs :func:`run_migrations` before serving,
so upgrading the image is all that's needed to migrate an existing volume's data.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import get_settings

logger = logging.getLogger("acme_lan.migrate")


def _migrations_dir() -> Path:
    """Locate the migrations directory across source checkouts and the container image."""
    import os

    override = os.environ.get("ACME_LAN_MIGRATIONS_DIR")
    candidates = [
        Path(override) if override else None,
        Path(__file__).resolve().parent.parent.parent / "migrations",  # source checkout
        Path.cwd() / "migrations",  # container (WORKDIR /app with COPYed migrations)
    ]
    for candidate in candidates:
        if candidate and (candidate / "env.py").exists():
            return candidate
    raise RuntimeError("Could not locate the migrations directory")


def sync_url(async_url: str) -> str:
    """Convert an async SQLAlchemy URL to the sync driver Alembic uses."""
    for async_driver, sync_driver in (
        ("+aiosqlite", ""),
        ("+asyncpg", "+psycopg2"),
        ("+psycopg_async", "+psycopg"),
    ):
        async_url = async_url.replace(async_driver, sync_driver)
    return async_url


def _alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    cfg.set_main_option("sqlalchemy.url", sync_url(database_url))
    return cfg


def run_migrations(database_url: str | None = None) -> None:
    """Upgrade the schema to head and apply data migrations. Idempotent."""
    settings = get_settings()
    database_url = database_url or settings.database_url
    cfg = _alembic_config(database_url)
    logger.info("Applying schema migrations (alembic upgrade head)")
    command.upgrade(cfg, "head")

    from sqlalchemy import create_engine

    from .migrations_data import run_data_migrations

    engine = create_engine(sync_url(database_url))
    try:
        with engine.begin() as conn:
            run_data_migrations(conn)
    finally:
        engine.dispose()
