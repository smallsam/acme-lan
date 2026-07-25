"""Issue and deploy certificates for managed hosts that can't run an ACME client.

For these devices acme-lan itself plays the ACME client: it generates the keypair and CSR,
obtains a real certificate through the Phase-1 upstream proxy (DNS-01), and pushes both the
certificate and key to the device via a deploy plugin.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .certstore.factory import get_cert_store
from .credentials import DecryptedCredential, decrypt_secret
from .deploy.base import DeployContext, DeployResult
from .deploy.factory import get_deploy_plugin
from .models import Certificate, ManagedHost, StoredCredential, utcnow

Issuer = Callable[[str], str]  # csr_pem -> fullchain_pem


def build_host_csr(domains: list[str]) -> tuple[str, str]:
    """Generate an RSA key and CSR for ``domains``; return (csr_pem, key_pem)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domains[0])]))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(d) for d in domains]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("ascii")
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return csr_pem, key_pem


async def _load_credential(
    host: ManagedHost, session: AsyncSession
) -> DecryptedCredential | None:
    if not host.credential_id:
        return None
    row = await session.get(StoredCredential, host.credential_id)
    if row is None:
        return None
    if row.provider == "local":
        secret = decrypt_secret(row.secret_encrypted)
    else:
        # Fetch from an external secret manager (Key Vault / Vault) at deploy time; the
        # secret is never persisted in acme-lan's database.
        from .secrets.factory import get_secret_provider

        provider = get_secret_provider(row.provider)
        secret = await run_in_threadpool(provider.get_secret, row.secret_reference)
    return DecryptedCredential(kind=row.kind, username=row.username, secret=secret)


def _default_issuer(csr_pem: str) -> str:
    from .upstream.fulfil import fulfil_order

    return fulfil_order(csr_pem)


async def renew_and_deploy(
    host: ManagedHost, session: AsyncSession, *, issuer: Issuer | None = None
) -> tuple[Certificate, DeployResult]:
    """Issue a fresh certificate for ``host`` and deploy it, recording the outcome."""
    issuer = issuer or _default_issuer
    credential = await _load_credential(host, session)
    device_mode = host.csr_source == "device"

    def _work() -> tuple[str, str | None, DeployResult]:
        plugin = get_deploy_plugin(host.deploy_plugin)
        config = dict(host.config)
        if device_mode:
            # Preferred: the device provides the CSR; its private key never reaches acme-lan.
            probe_ctx = DeployContext(host, "", None, credential, config)
            csr_pem = plugin.fetch_csr(probe_ctx)
            fullchain = issuer(csr_pem)
            install_ctx = DeployContext(host, fullchain, None, credential, config)
            return fullchain, None, plugin.install_cert(install_ctx)
        # Local: acme-lan generates the key + CSR and pushes both.
        csr_pem, key_pem = build_host_csr(list(host.domains))
        fullchain = issuer(csr_pem)
        ctx = DeployContext(host, fullchain, key_pem, credential, config)
        return fullchain, key_pem, plugin.deploy(ctx)

    fullchain, key_pem, result = await run_in_threadpool(_work)

    # Persist the cert (+ key, if we hold one) in the configured storage backend.
    store = get_cert_store()
    key_reference = await store.store(host.name or list(host.domains)[0], fullchain, key_pem)

    leaf = x509.load_pem_x509_certificates(fullchain.encode())[0]
    cert = Certificate(
        host_id=host.id,
        pem_chain=fullchain,
        domains=list(host.domains),
        serial=format(leaf.serial_number, "x"),
        subject=leaf.subject.rfc4514_string(),
        not_after=leaf.not_valid_after_utc,
        key_storage=store.name if key_pem else "none",
        key_reference=key_reference,
    )
    session.add(cert)
    host.last_deployed_at = utcnow()
    host.last_status = "deployed" if result.ok else f"error: {result.detail}"
    session.add(host)
    await session.commit()
    await session.refresh(cert)
    return cert, result


async def hosts_needing_renewal(
    session: AsyncSession, renew_before_days: int
) -> list[ManagedHost]:
    """Return enabled hosts whose latest certificate is missing or expiring soon."""
    hosts = (
        await session.execute(select(ManagedHost).where(ManagedHost.enabled == True))  # noqa: E712
    ).scalars().all()
    now = datetime.now(UTC)
    due: list[ManagedHost] = []
    for host in hosts:
        latest = (
            await session.execute(
                select(Certificate)
                .where(Certificate.host_id == host.id)
                .order_by(Certificate.not_after.desc())
            )
        ).scalars().first()
        if latest is None or latest.not_after is None:
            due.append(host)
            continue
        not_after = latest.not_after
        if not_after.tzinfo is None:
            not_after = not_after.replace(tzinfo=UTC)
        if (not_after - now).days <= renew_before_days:
            due.append(host)
    return due
