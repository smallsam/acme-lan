"""Tests that service private keys are never stored in plaintext."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

from acme_lan import config, keystore
from acme_lan.migrate import sync_url


def _key_material_rows(database_url: str):
    engine = create_engine(sync_url(database_url))
    try:
        with engine.connect() as conn:
            return conn.execute(text("SELECT name, key_encrypted FROM key_material")).fetchall()
    finally:
        engine.dispose()


async def test_account_key_stored_encrypted(fresh_db, tmp_path):
    # fresh_db configures a Fernet secret key and a temp DB.
    key = keystore.load_or_create_account_key("upstream-test")
    # Reloading returns the same key (persisted).
    again = keystore.load_or_create_account_key("upstream-test")
    assert key.thumbprint() == again.thumbprint()

    rows = _key_material_rows(os.environ["ACME_LAN_DATABASE_URL"])
    assert rows, "account key should be persisted"
    name, encrypted = rows[0]
    assert name == "acct:upstream-test"
    # The stored blob is Fernet ciphertext, not a PEM/JWK private key.
    assert "PRIVATE KEY" not in encrypted
    assert '"d"' not in encrypted  # RSA private exponent field of a JWK


async def test_ephemeral_when_no_secret_key(fresh_db):
    keystore._ephemeral.clear()
    os.environ.pop("ACME_LAN_SECRET_KEY", None)
    config.reset_settings_cache()

    key = keystore.load_or_create_account_key("no-secret")
    again = keystore.load_or_create_account_key("no-secret")
    assert key.thumbprint() == again.thumbprint()  # cached in memory

    # Nothing was written to the database.
    rows = _key_material_rows(os.environ["ACME_LAN_DATABASE_URL"])
    assert all(name != "acct:no-secret" for name, _ in rows)
