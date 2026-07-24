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
        assert any(h["id"] == host_id for h in listed)

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


async def test_deploy_plugins_endpoint(fresh_db):
    async with _client() as client:
        plugins = (await client.get("/api/deploy-plugins")).json()
        assert "local" in plugins and "ssh" in plugins
