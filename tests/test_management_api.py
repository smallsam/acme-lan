"""Tests for the management REST API and its optional admin-token gate."""

from __future__ import annotations

import os
from datetime import timedelta

import httpx

from acme_lan.models import utcnow


async def _seed_app(tmp_path, **env):
    # Clear toggles that other tests may have set, so each test starts clean.
    os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)
    os.environ["ACME_LAN_EXTERNAL_URL"] = "http://localhost:8000"
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/mgmt.sqlite"
    for key, value in env.items():
        os.environ[key] = value

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None

    from acme_lan.db import init_db, session_scope
    from acme_lan.models import Certificate, Order

    await init_db()
    async with session_scope() as session:
        order = Order(
            account_id="acct-1",
            identifiers=[{"type": "dns", "value": "db.lan.test"}],
            status="valid",
        )
        session.add(order)
        await session.flush()
        cert = Certificate(
            order_id=order.id,
            pem_chain="-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n",
            serial="ab12",
            subject="CN=db.lan.test",
            not_after=utcnow() + timedelta(days=80),
        )
        session.add(cert)
        await session.flush()
        order.certificate_id = cert.id
        session.add(order)
        await session.commit()
        cert_id = cert.id

    from acme_lan.main import create_app

    return create_app(), cert_id


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_stats_and_certificate_listing(tmp_path):
    app, cert_id = await _seed_app(tmp_path)
    async with _client(app) as client:
        stats = (await client.get("/api/stats")).json()
        assert stats["certificates_total"] == 1
        assert stats["orders_by_status"]["valid"] == 1

        certs = (await client.get("/api/certificates")).json()
        assert len(certs) == 1
        assert certs[0]["primary_domain"] == "db.lan.test"
        assert certs[0]["id"] == cert_id

        detail = (await client.get(f"/api/certificates/{cert_id}")).json()
        assert "BEGIN CERTIFICATE" in detail["pem_chain"]


async def test_admin_token_gating(tmp_path):
    app, _ = await _seed_app(tmp_path, ACME_LAN_ADMIN_TOKEN="s3cret")
    async with _client(app) as client:
        assert (await client.get("/api/stats")).status_code == 401
        ok = await client.get("/api/stats", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200


async def test_probe_endpoint_reports_unreachable(tmp_path):
    app, _ = await _seed_app(tmp_path)
    async with _client(app) as client:
        resp = await client.post(
            "/api/health/probe", json={"host": "127.0.0.1", "port": 1, "server_name": None}
        )
        assert resp.status_code == 200
        assert resp.json()["reachable"] is False


async def test_certificate_health_uses_resolver_override(tmp_path):
    import json

    app, cert_id = await _seed_app(
        tmp_path,
        ACME_LAN_HEALTH_RESOLVER_OVERRIDES=json.dumps({"db.lan.test": "127.0.0.1:9"}),
    )
    async with _client(app) as client:
        health = (await client.get(f"/api/certificates/{cert_id}/health")).json()
    # The probe went to the override target (127.0.0.1:9, closed) rather than the domain.
    assert health["host"] == "127.0.0.1"
    assert health["port"] == 9
    assert health["reachable"] is False


async def test_dashboard_is_served(tmp_path):
    app, _ = await _seed_app(tmp_path)
    async with _client(app) as client:
        # ACME + API routes still work alongside the static mount.
        assert (await client.get("/acme/directory")).status_code == 200
        index = await client.get("/")
        # The built dashboard is served if it has been compiled (src/acme_lan/web/dist).
        assert index.status_code in (200, 404)
