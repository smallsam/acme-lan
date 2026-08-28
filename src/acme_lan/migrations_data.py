"""Idempotent data migrations, run after the schema is upgraded.

Unlike schema (Alembic) migrations, these transform existing *data* — e.g. re-encrypting
stored secrets after a format change, or backfilling a new column. Each step has a stable
id and runs at most once (tracked in the ``data_migration`` table), so upgrading an
existing deployment applies exactly the new steps.

Register steps by appending ``(id, callable)`` to ``DATA_MIGRATIONS``. Each callable takes
a SQLAlchemy Connection and must be safe to run once.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import Connection, text

logger = logging.getLogger("acme_lan.migrate")

# (stable_id, step). Append-only; never renumber or remove applied ids.
DATA_MIGRATIONS: list[tuple[str, Callable[[Connection], None]]] = []


def _ensure_table(conn: Connection) -> None:
    conn.execute(
        text(
            "CREATE TABLE IF NOT EXISTS data_migration ("
            "id VARCHAR PRIMARY KEY, applied_at VARCHAR)"
        )
    )


def _applied(conn: Connection) -> set[str]:
    rows = conn.execute(text("SELECT id FROM data_migration")).fetchall()
    return {r[0] for r in rows}


def run_data_migrations(conn: Connection) -> int:
    """Run any not-yet-applied data migrations in order. Returns the number applied."""
    _ensure_table(conn)
    applied = _applied(conn)
    count = 0
    for step_id, step in DATA_MIGRATIONS:
        if step_id in applied:
            continue
        logger.info("Applying data migration %s", step_id)
        step(conn)
        conn.execute(
            text("INSERT INTO data_migration (id, applied_at) VALUES (:id, CURRENT_TIMESTAMP)"),
            {"id": step_id},
        )
        count += 1
    return count
