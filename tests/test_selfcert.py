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
    os.environ["ACME_LAN_SELF_CERT_KEY_PATH"] = str(tmp_path / "svc.key")
    from acme_lan import config

    config.reset_settings_cache()

    issuer = lambda csr: _chain("acme-lan.lan.test")  # noqa: E731

    assert await ensure_service_certificate(issuer=issuer) is True
    assert (tmp_path / "svc.pem").exists()
    assert (tmp_path / "svc.key").exists()
    assert (tmp_path / "svc.key").stat().st_mode & 0o777 == 0o600

    # Certificate still valid -> no reissue; force -> reissue.
    assert await ensure_service_certificate(issuer=issuer) is False
    assert await ensure_service_certificate(issuer=issuer, force=True) is True

    async with session_scope() as session:
        certs = (await session.execute(select(Certificate))).scalars().all()
        assert any("acme-lan.lan.test" in (c.domains or []) for c in certs)


async def test_no_service_domain_is_noop(fresh_db, tmp_path):
    os.environ.pop("ACME_LAN_SERVICE_DOMAIN", None)
    from acme_lan import config

    config.reset_settings_cache()
    assert await ensure_service_certificate(issuer=lambda csr: _chain("x")) is False
