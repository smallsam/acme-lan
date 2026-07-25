"""Tests for the ACME listener profile management API."""

from __future__ import annotations

import httpx


def _client():
    from acme_lan.main import create_app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")


async def test_profile_crud_and_validation(fresh_db):
    async with _client() as client:
        # ca_handler profile requires a known handler.
        bad = await client.post(
            "/api/acme-profiles",
            json={"name": "x", "upstream_type": "ca_handler", "ca_handler": "nope"},
        )
        assert bad.status_code == 400

        # acme profile requires a directory_url.
        bad2 = await client.post(
            "/api/acme-profiles", json={"name": "y", "upstream_type": "acme"}
        )
        assert bad2.status_code == 400

        created = await client.post(
            "/api/acme-profiles",
            json={
                "name": "digicert",
                "upstream_type": "acme",
                "directory_url": "https://acme.digicert.example/directory",
                "eab_kid": "kid-1",
                "eab_hmac_key": "super-secret-hmac",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["directory_url_public"] == "/acme/p/digicert/directory"
        assert body["eab_configured"] is True
        assert "eab_hmac_key" not in body  # secret never returned

        listed = (await client.get("/api/acme-profiles")).json()
        assert any(p["name"] == "digicert" for p in listed)

        patched = await client.patch("/api/acme-profiles/digicert", json={"enabled": False})
        assert patched.json()["enabled"] is False

        assert (await client.delete("/api/acme-profiles/digicert")).status_code == 204
        assert (await client.get("/api/acme-profiles/digicert")).status_code == 404


async def test_reserved_names_rejected(fresh_db):
    async with _client() as client:
        for name in ("default", "p"):
            resp = await client.post(
                "/api/acme-profiles",
                json={"name": name, "upstream_type": "acme", "directory_url": "https://x/dir"},
            )
            assert resp.status_code == 400
