"""Tests for pluggable certificate/key storage backends."""

from __future__ import annotations

import pytest

from acme_lan.certstore.azure import AzureKeyVaultStore
from acme_lan.certstore.base import CertStore
from acme_lan.certstore.local import LocalCertStore
from acme_lan.certstore.vault import VaultCertStore
from acme_lan.db import session_scope
from acme_lan.models import KeyMaterial


async def _roundtrip(store: CertStore):
    ref = await store.store("db.lan.test", "CERTPEM", "KEYPEM")
    bundle = await store.fetch(ref)
    assert bundle.cert_pem == "CERTPEM"
    assert bundle.key_pem == "KEYPEM"
    # No-key bundle.
    ref2 = await store.store("nokey.lan.test", "CERTONLY", None)
    assert (await store.fetch(ref2)).key_pem is None


async def test_local_store_roundtrip_and_encryption(fresh_db):
    store = LocalCertStore()
    ref = await store.store("db.lan.test", "CERTPEM", "SECRETKEY")
    async with session_scope() as session:
        row = await session.get(KeyMaterial, ref)
        assert row.key_encrypted is not None
        assert "SECRETKEY" not in row.key_encrypted  # stored encrypted at rest
    bundle = await store.fetch(ref)
    assert bundle.key_pem == "SECRETKEY"
    await store.delete(ref)
    with pytest.raises(KeyError):
        await store.fetch(ref)


class _FakeAzureSecret:
    def __init__(self, value):
        self.value = value


class _FakeAzureClient:
    def __init__(self):
        self.secrets = {}

    def set_secret(self, name, value):
        self.secrets[name] = value

    def get_secret(self, name):
        if name not in self.secrets:
            raise KeyError(name)
        return _FakeAzureSecret(self.secrets[name])

    def begin_delete_secret(self, name):
        self.secrets.pop(name, None)


async def test_azure_store_roundtrip():
    store = AzureKeyVaultStore("https://vault.example", client=_FakeAzureClient())
    await _roundtrip(store)


class _FakeKvV2:
    def __init__(self):
        self.store = {}

    def create_or_update_secret(self, path, mount_point, secret):
        self.store[(mount_point, path)] = secret

    def read_secret_version(self, path, mount_point):
        return {"data": {"data": self.store[(mount_point, path)]}}

    def delete_metadata_and_all_versions(self, path, mount_point):
        self.store.pop((mount_point, path), None)


class _FakeHvacClient:
    def __init__(self):
        self.secrets = type("S", (), {})()
        self.secrets.kv = type("KV", (), {})()
        self.secrets.kv.v2 = _FakeKvV2()


async def test_vault_store_roundtrip():
    store = VaultCertStore("http://vault", "token", "secret", "acme-lan", client=_FakeHvacClient())
    ref = await store.store("db.lan.test", "CERTPEM", "KEYPEM")
    assert ref == "acme-lan/db.lan.test"
    bundle = await store.fetch(ref)
    assert bundle.cert_pem == "CERTPEM" and bundle.key_pem == "KEYPEM"


def test_factory_selects_backend(monkeypatch):
    from acme_lan import config
    from acme_lan.certstore.factory import get_cert_store

    monkeypatch.setenv("ACME_LAN_CERT_STORE_BACKEND", "local")
    config.reset_settings_cache()
    assert isinstance(get_cert_store(), LocalCertStore)
