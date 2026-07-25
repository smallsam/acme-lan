"""Encrypted storage for the service's own private keys (never plaintext at rest).

Holds the upstream ACME account key and the self-service TLS key. When a Fernet
``ACME_LAN_SECRET_KEY`` is configured they are stored encrypted in the database; otherwise
they are kept in memory only (regenerated per process) so nothing sensitive is written to
disk. This is separate from issued certificate keys, which for the ACME proxy and
CSR-from-device flows never touch acme-lan at all.
"""

from __future__ import annotations

import json
import logging
import uuid

import josepy
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, text

from .config import get_settings
from .credentials import decrypt_secret, encrypt_secret
from .migrate import sync_url

logger = logging.getLogger("acme_lan.keystore")

_engines: dict[str, object] = {}
_ephemeral: dict[str, str] = {}
_warned = False


def _sync_engine():
    url = sync_url(get_settings().database_url)
    if url not in _engines:
        _engines[url] = create_engine(url, future=True)
    return _engines[url]


def get_material(name: str) -> str | None:
    """Return decrypted key material stored under ``name`` (encrypted DB backend)."""
    engine = _sync_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT key_encrypted FROM key_material WHERE name = :n LIMIT 1"), {"n": name}
        ).fetchone()
    if row is None or not row[0]:
        return None
    return decrypt_secret(row[0])


def put_material(name: str, value: str) -> None:
    engine = _sync_engine()
    enc = encrypt_secret(value)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM key_material WHERE name = :n"), {"n": name})
        conn.execute(
            text(
                "INSERT INTO key_material (id, name, cert_pem, key_encrypted, created_at) "
                "VALUES (:id, :n, '', :e, datetime('now'))"
            ),
            {"id": uuid.uuid4().hex, "n": name, "e": enc},
        )


def _warn_ephemeral() -> None:
    global _warned
    if not _warned:
        logger.warning(
            "ACME_LAN_SECRET_KEY is not set: service private keys are kept in memory only "
            "and regenerated on restart. Set it to persist them (encrypted)."
        )
        _warned = True


def load_or_create_account_key(name: str) -> josepy.JWKRSA:
    """Load (or generate + persist) the upstream ACME account key ``name``."""
    settings = get_settings()
    if settings.secret_key:
        existing = get_material(f"acct:{name}")
        if existing:
            return josepy.JWKRSA.json_loads(existing)
        key = josepy.JWKRSA(key=josepy.ComparableRSAKey(
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ))
        put_material(f"acct:{name}", json.dumps(key.to_json()))
        return key

    _warn_ephemeral()
    if name not in _ephemeral:
        key = josepy.JWKRSA(key=josepy.ComparableRSAKey(
            rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ))
        _ephemeral[name] = json.dumps(key.to_json())
    return josepy.JWKRSA.json_loads(_ephemeral[name])
