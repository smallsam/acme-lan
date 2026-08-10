"""Tests for the managed-host and credential management API."""

from __future__ import annotations

import httpx


def _client():
    from acme_lan.main import create_app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")


async def test_host_crud(fresh_db):
    async with _client() as client:
        created = await client.post(
            "/api/hosts",
            json={
                "name": "esxi01",
                "domains": ["esxi01.lan.test"],
                "address": "192.168.3.5",
                "port": 443,
                "deploy_plugin": "local",
                "config": {"cert_path": "/tmp/c", "key_path": "/tmp/k"},
            },
        )
        assert created.status_code == 201
        host = created.json()
        assert host["name"] == "esxi01"
        host_id = host["id"]

        listed = (await client.get("/api/hosts")).json()
        assert listed["total"] == 1
        assert any(h["id"] == host_id for h in listed["items"])

        patched = await client.patch(f"/api/hosts/{host_id}", json={"enabled": False})
        assert patched.json()["enabled"] is False

        assert (await client.delete(f"/api/hosts/{host_id}")).status_code == 204
        assert (await client.get(f"/api/hosts/{host_id}")).status_code == 404


async def test_unknown_deploy_plugin_rejected(fresh_db):
    async with _client() as client:
        resp = await client.post(
            "/api/hosts",
            json={"name": "x", "domains": ["x.lan.test"], "address": "1.2.3.4",
                  "deploy_plugin": "bogus"},
        )
        assert resp.status_code == 400


async def test_credentials_are_write_only(fresh_db):
    async with _client() as client:
        created = await client.post(
            "/api/credentials",
            json={"name": "esxi-root", "kind": "password", "username": "root",
                  "secret": "sup3rsecret"},
        )
        assert created.status_code == 201
        body = created.json()
        assert "secret" not in body and "secret_encrypted" not in body

        listed = (await client.get("/api/credentials")).json()
        assert listed[0]["username"] == "root"
        assert "secret" not in listed[0]


async def test_deploy_plugins_endpoint_returns_schema(fresh_db):
    async with _client() as client:
        plugins = (await client.get("/api/deploy-plugins")).json()
        by_name = {p["name"]: p for p in plugins}
        assert {"local", "ssh"} <= by_name.keys()
        # Each plugin declares the config fields the UI should render.
        ssh = by_name["ssh"]
        assert ssh["supports_csr_retrieval"] is True
        keys = {f["key"] for f in ssh["fields"]}
        assert {"remote_cert_path", "remote_key_path", "csr_command", "port"} <= keys
        # Fields carry the mode(s) they apply to, so the form can filter by csr_source.
        remote_key = next(f for f in ssh["fields"] if f["key"] == "remote_key_path")
        assert remote_key["required"] is True
        assert "local" in remote_key["modes"]


async def test_host_certificate_linkage(fresh_db):
    from datetime import UTC, datetime, timedelta

    from acme_lan.db import session_scope
    from acme_lan.models import Certificate, ManagedHost

    async with session_scope() as session:
        host = ManagedHost(name="esxi01", domains=["esxi01.lan.test"], address="192.168.3.5")
        session.add(host)
        await session.flush()
        session.add(
            Certificate(
                host_id=host.id, domains=["esxi01.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=40),
            )
        )
        await session.commit()
        host_id = host.id

    async with _client() as client:
        # host -> its latest certificate + count
        host_view = (await client.get(f"/api/hosts/{host_id}")).json()
        assert host_view["certificate_count"] == 1
        assert host_view["latest_certificate"]["primary_domain"] == "esxi01.lan.test"

        host_certs = (await client.get(f"/api/hosts/{host_id}/certificates")).json()
        assert len(host_certs) == 1

        # certificate -> its device host (reverse link)
        certs = (await client.get("/api/certificates")).json()["items"]
        cert = next(c for c in certs if c["host_id"] == host_id)
        assert cert["host_name"] == "esxi01"
