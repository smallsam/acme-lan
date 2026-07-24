"""Tests for managed-host issuance/deploy orchestration and renewal selection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from acme_lan.db import session_scope
from acme_lan.hosts import hosts_needing_renewal, renew_and_deploy
from acme_lan.models import Certificate, ManagedHost


def _self_signed_chain(domain: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=90))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def test_renew_and_deploy_local(fresh_db, tmp_path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    async with session_scope() as session:
        host = ManagedHost(
            name="printer",
            domains=["printer.lan.test"],
            address="127.0.0.1",
            deploy_plugin="local",
            config={"cert_path": str(cert_path), "key_path": str(key_path)},
        )
        session.add(host)
        await session.commit()

        # Inject a fake issuer so no upstream CA is needed for this unit test.
        cert, result = await renew_and_deploy(
            host, session, issuer=lambda csr_pem: _self_signed_chain("printer.lan.test")
        )

    assert result.ok, result.detail
    assert cert_path.exists() and key_path.exists()
    assert cert.host_id == host.id
    assert cert.domains == ["printer.lan.test"]
    assert host.last_status == "deployed"

    # The issued key was persisted in the configured store (local) and is retrievable.
    assert cert.key_storage == "local"
    assert cert.key_reference
    from acme_lan.certstore.factory import get_cert_store

    bundle = await get_cert_store().fetch(cert.key_reference)
    assert bundle.key_pem is not None


async def test_hosts_needing_renewal(fresh_db):
    async with session_scope() as session:
        # Host A: no cert yet -> due.
        host_a = ManagedHost(name="a", domains=["a.lan.test"], address="127.0.0.1")
        # Host B: fresh cert -> not due.
        host_b = ManagedHost(name="b", domains=["b.lan.test"], address="127.0.0.1")
        # Host C: cert expiring soon -> due.
        host_c = ManagedHost(name="c", domains=["c.lan.test"], address="127.0.0.1")
        # Host D: disabled -> never due.
        host_d = ManagedHost(name="d", domains=["d.lan.test"], address="127.0.0.1", enabled=False)
        for h in (host_a, host_b, host_c, host_d):
            session.add(h)
        await session.flush()

        session.add(
            Certificate(host_id=host_b.id, not_after=datetime.now(UTC) + timedelta(days=80))
        )
        session.add(
            Certificate(host_id=host_c.id, not_after=datetime.now(UTC) + timedelta(days=5))
        )
        session.add(
            Certificate(host_id=host_d.id, not_after=datetime.now(UTC) + timedelta(days=1))
        )
        await session.commit()

        due = await hosts_needing_renewal(session, renew_before_days=30)
        due_names = {h.name for h in due}

    assert due_names == {"a", "c"}
