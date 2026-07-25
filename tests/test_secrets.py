"""Tests for remote secret providers and remote device-push credential resolution."""

from __future__ import annotations

import httpx

from acme_lan.db import session_scope
from acme_lan.models import ManagedHost, StoredCredential
from acme_lan.secrets.azure import AzureKeyVaultSecrets
from acme_lan.secrets.vault import VaultSecrets


class _FakeAzureSecret:
    def __init__(self, value):
        self.value = value


class _FakeAzureClient:
    def __init__(self, data):
        self.data = data

    def get_secret(self, name):
        return _FakeAzureSecret(self.data[name])


def test_azure_secret_provider():
    provider = AzureKeyVaultSecrets("https://v", client=_FakeAzureClient({"esxi-root": "hunter2"}))
    assert provider.get_secret("esxi-root") == "hunter2"


class _FakeKvV2:
    def read_secret_version(self, path, mount_point):
        return {"data": {"data": {"value": f"secret@{mount_point}/{path}", "password": "pw"}}}


class _FakeHvac:
    def __init__(self):
        self.secrets = type("S", (), {})()
        self.secrets.kv = type("KV", (), {})()
        self.secrets.kv.v2 = _FakeKvV2()


def test_vault_secret_provider_default_and_field():
    provider = VaultSecrets("http://v", "tok", "secret", client=_FakeHvac())
    assert provider.get_secret("acme-lan/esxi") == "secret@secret/acme-lan/esxi"
    assert provider.get_secret("acme-lan/esxi#password") == "pw"


async def test_remote_credential_resolved_at_deploy(fresh_db, monkeypatch):
    async with session_scope() as session:
        cred = StoredCredential(
            name="esxi", kind="password", username="root",
            provider="vault", secret_reference="acme-lan/esxi#password",
        )
        session.add(cred)
        await session.flush()
        host = ManagedHost(
            name="esxi01", domains=["esxi01.lan"], address="1.2.3.4", credential_id=cred.id
        )
        session.add(host)
        await session.commit()
        host_id = host.id

    class _FakeProvider:
        def get_secret(self, reference):
            return f"resolved:{reference}"

    monkeypatch.setattr(
        "acme_lan.secrets.factory.get_secret_provider", lambda name: _FakeProvider()
    )

    from acme_lan.hosts import _load_credential

    async with session_scope() as session:
        host = await session.get(ManagedHost, host_id)
        decrypted = await _load_credential(host, session)

    assert decrypted.username == "root"
    assert decrypted.secret == "resolved:acme-lan/esxi#password"


def _api_client():
    from acme_lan.main import create_app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")


async def test_create_remote_credential_stores_no_secret(fresh_db):
    async with _api_client() as client:
        # remote credential requires a reference, not a secret
        bad = await client.post(
            "/api/credentials",
            json={"name": "x", "kind": "password", "username": "root", "provider": "vault"},
        )
        assert bad.status_code == 400

        created = await client.post(
            "/api/credentials",
            json={
                "name": "esxi", "kind": "password", "username": "root",
                "provider": "vault", "secret_reference": "acme-lan/esxi#password",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["provider"] == "vault"
        assert body["secret_reference"] == "acme-lan/esxi#password"

    # The secret itself was never stored in the DB.
    async with session_scope() as session:
        from sqlalchemy import select

        rows = (await session.execute(select(StoredCredential))).scalars().all()
        assert rows[0].secret_encrypted == ""
