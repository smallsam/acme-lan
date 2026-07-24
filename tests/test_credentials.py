"""Tests for the encrypted credential store."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from acme_lan import config
from acme_lan.credentials import CredentialError, decrypt_secret, encrypt_secret


def _set_key(key: str | None) -> None:
    if key is None:
        os.environ.pop("ACME_LAN_SECRET_KEY", None)
    else:
        os.environ["ACME_LAN_SECRET_KEY"] = key
    config.reset_settings_cache()


def test_encrypt_decrypt_round_trip():
    _set_key(Fernet.generate_key().decode())
    ciphertext = encrypt_secret("hunter2")
    assert ciphertext != "hunter2"
    assert decrypt_secret(ciphertext) == "hunter2"


def test_missing_key_raises():
    _set_key(None)
    with pytest.raises(CredentialError):
        encrypt_secret("x")


def test_wrong_key_cannot_decrypt():
    _set_key(Fernet.generate_key().decode())
    ciphertext = encrypt_secret("secret")
    _set_key(Fernet.generate_key().decode())  # rotate to a different key
    with pytest.raises(CredentialError):
        decrypt_secret(ciphertext)
