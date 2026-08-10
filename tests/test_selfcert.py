"""Tests for acme-lan issuing and refreshing its own service certificate."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select

from acme_lan.db import session_scope
from acme_lan.models import Certificate
from acme_lan.selfcert import ensure_service_certificate


def _chain(domain: str, days: int = 90) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(n)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


async def test_ensure_service_certificate(fresh_db, tmp_path):
    os.environ["ACME_LAN_SERVICE_DOMAIN"] = "acme-lan.lan.test"
    os.environ["ACME_LAN_SELF_CERT_PATH"] = str(tmp_path / "svc.pem")
    from acme_lan import config

    config.reset_settings_cache()

    issuer = lambda csr: _chain("acme-lan.lan.test")  # noqa: E731

    assert await ensure_service_certificate(issuer=issuer) is True
    # Only the public cert is written to disk; the key is NOT.
    assert (tmp_path / "svc.pem").exists()
    assert not (tmp_path / "svc.key").exists()

    # The private key is retrievable but stored encrypted (via the keystore).
    from acme_lan import keystore
    from acme_lan.selfcert import materialize_service_key

    assert keystore.get_material("selfcert:acme-lan.lan.test") is not None
    key_path = materialize_service_key("acme-lan.lan.test")
    assert key_path
    with open(key_path) as fh:
        assert "PRIVATE KEY" in fh.read()

    # Certificate still valid -> no reissue; force -> reissue.
    assert await ensure_service_certificate(issuer=issuer) is False
    assert await ensure_service_certificate(issuer=issuer, force=True) is True

    async with session_scope() as session:
        certs = (await session.execute(select(Certificate))).scalars().all()
        assert any("acme-lan.lan.test" in (c.domains or []) for c in certs)


async def test_no_service_domain_is_noop(fresh_db, tmp_path):
    # Unset, service_domain derives from external_url (localhost under fresh_db) — a
    # dot-less name is not something an upstream CA can issue for, so this is a noop.
    os.environ.pop("ACME_LAN_SERVICE_DOMAIN", None)
    from acme_lan import config

    config.reset_settings_cache()
    assert await ensure_service_certificate(issuer=lambda csr: _chain("x")) is False


async def test_service_domain_derived_from_external_url(fresh_db, tmp_path):
    os.environ.pop("ACME_LAN_SERVICE_DOMAIN", None)
    os.environ["ACME_LAN_EXTERNAL_URL"] = "https://svc.lan.test:8443"
    os.environ["ACME_LAN_SELF_CERT_PATH"] = str(tmp_path / "svc.pem")
    from acme_lan import config

    config.reset_settings_cache()
    assert config.get_settings().service_domain == "svc.lan.test"
    assert await ensure_service_certificate(issuer=lambda csr: _chain("svc.lan.test")) is True
    assert (tmp_path / "svc.pem").exists()


async def test_self_cert_requires_secret_key(fresh_db, tmp_path):
    # Without a secret key we must refuse rather than write a plaintext key to disk.
    os.environ["ACME_LAN_SERVICE_DOMAIN"] = "x.lan.test"
    os.environ["ACME_LAN_SELF_CERT_PATH"] = str(tmp_path / "c.pem")
    os.environ.pop("ACME_LAN_SECRET_KEY", None)
    from acme_lan import config

    config.reset_settings_cache()
    assert await ensure_service_certificate(issuer=lambda csr: _chain("x.lan.test")) is False
    assert not (tmp_path / "c.pem").exists()
