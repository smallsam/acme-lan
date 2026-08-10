"""acme-lan obtains and renews its own TLS certificate — without a plaintext key at rest.

The certificate (public) is written to ``self_cert_path`` for serving; the private key is
stored **encrypted** via the keystore and only materialized into an in-memory file
descriptor (memfd on Linux) when uvicorn needs it — it is never written to disk in the
clear. Requires ``ACME_LAN_SECRET_KEY``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import UTC, datetime

from cryptography import x509
from fastapi.concurrency import run_in_threadpool

from . import keystore
from .config import get_settings
from .db import session_scope
from .hosts import Issuer, build_host_csr
from .models import Certificate, utcnow

logger = logging.getLogger("acme_lan.selfcert")


def _key_name(domain: str) -> str:
    return f"selfcert:{domain}"


def _needs_issue(cert_path: str, renew_before_days: int) -> bool:
    if not os.path.exists(cert_path):
        return True
    try:
        with open(cert_path, "rb") as fh:
            leaf = x509.load_pem_x509_certificates(fh.read())[0]
    except Exception:  # noqa: BLE001 - unreadable/garbage -> reissue
        return True
    return (leaf.not_valid_after_utc - datetime.now(UTC)).days <= renew_before_days


def _default_issuer(csr_pem: str) -> str:
    from .upstream.fulfil import fulfil_order

    return fulfil_order(csr_pem)


async def ensure_service_certificate(*, issuer: Issuer | None = None, force: bool = False) -> bool:
    """Ensure a current service certificate exists. Returns True if (re)issued."""
    settings = get_settings()
    domain = settings.service_domain
    if not domain or "." not in domain:
        # service_domain defaults to the external_url hostname; a dot-less name like
        # "localhost" is nothing an upstream CA can issue for — treat as unconfigured.
        return False
    if not settings.secret_key:
        logger.error(
            "Self-service TLS requires ACME_LAN_SECRET_KEY (to store the key encrypted); "
            "skipping so no plaintext key is written to disk."
        )
        return False
    if not force and not _needs_issue(settings.self_cert_path, settings.renew_before_days):
        return False

    issuer = issuer or _default_issuer

    def _issue() -> tuple[str, str]:
        csr_pem, key_pem = build_host_csr([domain])
        fullchain = issuer(csr_pem)
        # Persist the key encrypted; write only the public cert to disk.
        keystore.put_material(_key_name(domain), key_pem)
        return fullchain, key_pem

    fullchain, _key_pem = await run_in_threadpool(_issue)

    parent = os.path.dirname(settings.self_cert_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(settings.self_cert_path, "w") as fh:
        fh.write(fullchain)

    leaf = x509.load_pem_x509_certificates(fullchain.encode())[0]
    async with session_scope() as session:
        session.add(
            Certificate(
                pem_chain=fullchain,
                domains=[domain],
                subject=leaf.subject.rfc4514_string(),
                serial=format(leaf.serial_number, "x"),
                not_after=leaf.not_valid_after_utc,
                key_storage="encrypted",
                key_reference=_key_name(domain),
                issued_at=utcnow(),
            )
        )
        await session.commit()
    logger.info("Service certificate for %s issued (key stored encrypted)", domain)
    return True


def materialize_service_key(domain: str) -> str | None:
    """Decrypt the service key into an in-memory fd and return a path uvicorn can load.

    Uses ``memfd_create`` so the plaintext key never touches disk; falls back to a 0600
    temporary file on platforms without memfd.
    """
    key_pem = keystore.get_material(_key_name(domain))
    if not key_pem:
        return None
    data = key_pem.encode()
    try:
        fd = os.memfd_create(f"acme-lan-{domain}")  # Linux only; fd stays open for the process
        os.write(fd, data)
        os.lseek(fd, 0, 0)
        return f"/proc/self/fd/{fd}"
    except (AttributeError, OSError):
        fd, path = tempfile.mkstemp(prefix="acme-lan-selfkey-", suffix=".pem")
        os.chmod(path, 0o600)
        os.write(fd, data)
        os.close(fd)
        logger.warning("memfd unavailable; wrote the service key to a 0600 temp file %s", path)
        return path


async def run_self_cert_maintainer(stop_event: asyncio.Event) -> None:
    """Ensure the service cert on startup, then refresh it on an interval."""
    interval = get_settings().self_cert_refresh_interval_seconds
    while not stop_event.is_set():
        try:
            await ensure_service_certificate()
        except Exception:  # noqa: BLE001
            logger.exception("Service certificate maintenance failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
