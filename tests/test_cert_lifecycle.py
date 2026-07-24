"""Tests for certificate lifecycle: expiry status, retirement, expiring query."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from acme_lan.certlifecycle import expiring_certificates, expiry_info
from acme_lan.db import session_scope
from acme_lan.models import Certificate


def _client():
    from acme_lan.main import create_app

    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://t")


def test_expiry_info():
    soon = Certificate(not_after=datetime.now(UTC) + timedelta(days=5), domains=["a"])
    info = expiry_info(soon, warn_days=21)
    assert info["expiring_soon"] is True
    assert info["expired"] is False
    assert 4 <= info["days_until_expiry"] <= 5

    retired = Certificate(
        not_after=datetime.now(UTC) + timedelta(days=5), domains=["a"], retired=True
    )
    assert expiry_info(retired, warn_days=21)["expiring_soon"] is False


async def test_expiring_uses_latest_per_group_and_skips_retired(fresh_db):
    async with session_scope() as session:
        # Two certs for the same host: an old expiring one and a fresh renewal.
        session.add(
            Certificate(
                host_id="h1",
                domains=["db.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=3),
                issued_at=datetime.now(UTC) - timedelta(days=80),
            )
        )
        session.add(
            Certificate(
                host_id="h1",
                domains=["db.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=80),
                issued_at=datetime.now(UTC),
            )
        )
        # A different host expiring soon.
        session.add(
            Certificate(
                host_id="h2",
                domains=["print.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=2),
            )
        )
        # Retired, expiring: must be ignored.
        session.add(
            Certificate(
                host_id="h3",
                domains=["old.lan.test"],
                not_after=datetime.now(UTC) + timedelta(days=1),
                retired=True,
            )
        )
        await session.commit()

        expiring = await expiring_certificates(session, warn_days=21)
        hosts = {c.host_id for c in expiring}

    # h1's renewal is fresh so it's not expiring; h2 is; h3 retired -> excluded.
    assert hosts == {"h2"}


async def test_retire_and_unretire_via_api(fresh_db):
    async with session_scope() as session:
        cert = Certificate(
            host_id="h1", domains=["db.lan.test"],
            not_after=datetime.now(UTC) + timedelta(days=2),
        )
        session.add(cert)
        await session.commit()
        cert_id = cert.id

    async with _client() as client:
        expiring = (await client.get("/api/certificates/expiring")).json()
        assert any(c["id"] == cert_id for c in expiring)

        retired = (
            await client.post(
                f"/api/certificates/{cert_id}/retire", json={"reason": "decommissioned"}
            )
        ).json()
        assert retired["retired"] is True
        assert retired["retired_reason"] == "decommissioned"

        # No longer in the expiring list once retired.
        expiring = (await client.get("/api/certificates/expiring")).json()
        assert all(c["id"] != cert_id for c in expiring)

        unretired = (await client.post(f"/api/certificates/{cert_id}/unretire")).json()
        assert unretired["retired"] is False
