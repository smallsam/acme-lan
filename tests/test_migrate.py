"""Tests for automatic schema + data migrations."""

from __future__ import annotations

import sqlite3

from sqlalchemy import create_engine

from acme_lan.migrate import run_migrations, sync_url
from acme_lan.migrations_data import run_data_migrations


def test_sync_url_conversion():
    assert sync_url("sqlite+aiosqlite:///./x.db") == "sqlite:///./x.db"
    assert sync_url("postgresql+asyncpg://u@h/db") == "postgresql+psycopg2://u@h/db"


def test_run_migrations_creates_schema_and_is_idempotent(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/t.db"
    run_migrations(url)
    run_migrations(url)  # second run must be a no-op, not an error

    con = sqlite3.connect(f"{tmp_path}/t.db")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert {"account", "certificate", "managed_host", "acme_profile"} <= tables
    assert "alembic_version" in tables
    assert "data_migration" in tables


def test_data_migrations_run_once(tmp_path, monkeypatch):
    calls = []

    def _step(conn):
        calls.append(1)

    monkeypatch.setattr("acme_lan.migrations_data.DATA_MIGRATIONS", [("test-step", _step)])

    engine = create_engine(f"sqlite:///{tmp_path}/d.db")
    with engine.begin() as conn:
        assert run_data_migrations(conn) == 1
    with engine.begin() as conn:
        assert run_data_migrations(conn) == 0  # already applied
    engine.dispose()
    assert calls == [1]
