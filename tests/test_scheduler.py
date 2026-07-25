"""Tests for the auto-renew scheduler tick."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from acme_lan.db import session_scope
from acme_lan.models import Certificate, ManagedHost
from acme_lan.scheduler import renew_due_hosts


def _chain(domain: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(n)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=90))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def test_renew_due_hosts_renews_only_due(fresh_db, tmp_path):
    async with session_scope() as session:
        due = ManagedHost(
            name="due",
            domains=["due.lan.test"],
            address="127.0.0.1",
            deploy_plugin="local",
            csr_source="local",
            config={
                "cert_path": str(tmp_path / "due-cert.pem"),
                "key_path": str(tmp_path / "due-key.pem"),
            },
        )
        fresh = ManagedHost(name="fresh", domains=["fresh.lan.test"], address="127.0.0.1")
        session.add(due)
        session.add(fresh)
        await session.flush()
        session.add(
            Certificate(host_id=fresh.id, not_after=datetime.now(UTC) + timedelta(days=80))
        )
        await session.commit()

    results = await renew_due_hosts(issuer=lambda csr: _chain("due.lan.test"))

    names = {r["host"]: r["ok"] for r in results}
    assert names == {"due": True}  # only the due host was renewed
    assert (tmp_path / "due-cert.pem").exists()

    # A follow-up tick finds nothing due (the host now has a fresh cert).
    assert await renew_due_hosts(issuer=lambda csr: _chain("due.lan.test")) == []
