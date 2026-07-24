"""Encrypted credential storage for device logins (Fernet symmetric encryption).

Secrets (device passwords or SSH private keys) are encrypted at rest with a key derived
from ``ACME_LAN_SECRET_KEY``. Only this server can decrypt them, and only to deploy a
certificate to a device.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class CredentialError(RuntimeError):
    pass


@dataclass
class DecryptedCredential:
    kind: str  # "password" | "ssh_key"
    username: str
    secret: str


def _fernet() -> Fernet:
    key = get_settings().secret_key
    if not key:
        raise CredentialError(
            "ACME_LAN_SECRET_KEY is not configured; cannot encrypt/decrypt credentials"
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise CredentialError("ACME_LAN_SECRET_KEY is not a valid Fernet key") from exc


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CredentialError("Could not decrypt stored secret (wrong key?)") from exc


def generate_key() -> str:
    """Return a fresh Fernet key (for operators setting up ``ACME_LAN_SECRET_KEY``)."""
    return Fernet.generate_key().decode()
