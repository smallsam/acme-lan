"""Tests for the two device-push modes: CSR-from-device vs local key."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from acme_lan.db import session_scope
from acme_lan.deploy.base import DeployContext, DeployPlugin, DeployResult
from acme_lan.deploy.factory import register_plugin
from acme_lan.hosts import renew_and_deploy
from acme_lan.models import ManagedHost


def _device_csr(domain: str) -> str:
    # Simulates a CSR generated on the device, whose key never leaves it.
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


def _chain(domain: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(n)
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CA")]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=90))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


class _FakeDevicePlugin(DeployPlugin):
    name = "fake_device"
    supports_csr_retrieval = True
    last = {}

    def fetch_csr(self, ctx: DeployContext) -> str:
        csr = _device_csr(ctx.host.domains[0])
        _FakeDevicePlugin.last["fetched_csr"] = csr
        return csr

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        _FakeDevicePlugin.last["installed"] = ctx.fullchain_pem
        _FakeDevicePlugin.last["key_in_ctx"] = ctx.private_key_pem
        return DeployResult(True, "installed cert only")

    def deploy(self, ctx: DeployContext) -> DeployResult:  # must NOT be called in device mode
        _FakeDevicePlugin.last["deploy_called"] = True
        return DeployResult(True)


async def test_device_mode_never_holds_private_key(fresh_db):
    register_plugin(_FakeDevicePlugin)
    _FakeDevicePlugin.last = {}

    captured = {}

    def issuer(csr_pem: str) -> str:
        captured["csr"] = csr_pem
        return _chain("cam.lan.test")

    async with session_scope() as session:
        host = ManagedHost(
            name="camera",
            domains=["cam.lan.test"],
            address="127.0.0.1",
            deploy_plugin="fake_device",
            csr_source="device",
        )
        session.add(host)
        await session.commit()
        cert, result = await renew_and_deploy(host, session, issuer=issuer)

    assert result.ok
    # The issuer signed the *device's* CSR.
    assert captured["csr"] == _FakeDevicePlugin.last["fetched_csr"]
    # Only the cert was installed; no key was ever in the deploy context.
    assert _FakeDevicePlugin.last["installed"] == cert.pem_chain
    assert _FakeDevicePlugin.last["key_in_ctx"] is None
    assert "deploy_called" not in _FakeDevicePlugin.last
    # acme-lan did not store a private key for this cert.
    assert cert.key_storage == "none"
