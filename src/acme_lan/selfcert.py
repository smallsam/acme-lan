"""acme-lan obtains and renews its *own* TLS certificate.

Once a service domain and an upstream are configured, acme-lan issues a certificate for
its own hostname (via the default upstream proxy) and writes it to disk so uvicorn can
serve the admin UI and ACME endpoints over trusted HTTPS — eliminating certificate
warnings for the whole LAN. The cert is tracked like any other and auto-renewed.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime

from cryptography import x509
from fastapi.concurrency import run_in_threadpool

from .config import get_settings
from .db import session_scope
from .hosts import Issuer, build_host_csr
from .models import Certificate, utcnow

logger = logging.getLogger("acme_lan.selfcert")


def _needs_issue(cert_path: str, renew_before_days: int) -> bool:
    if not os.path.exists(cert_path):
        return True
    try:
        with open(cert_path, "rb") as fh:
            leaf = x509.load_pem_x509_certificates(fh.read())[0]
    except Exception:  # noqa: BLE001 - unreadable/garbage -> reissue
        return True
    not_after = leaf.not_valid_after_utc
    return (not_after - datetime.now(UTC)).days <= renew_before_days


def _default_issuer(csr_pem: str) -> str:
    from .upstream.fulfil import fulfil_order

    return fulfil_order(csr_pem)


async def ensure_service_certificate(*, issuer: Issuer | None = None, force: bool = False) -> bool:
    """Ensure a current service certificate exists on disk. Returns True if (re)issued."""
    settings = get_settings()
    if not settings.service_domain:
        return False
    if not force and not _needs_issue(settings.self_cert_path, settings.renew_before_days):
        return False

    issuer = issuer or _default_issuer
    domain = settings.service_domain

    def _issue() -> tuple[str, str]:
        csr_pem, key_pem = build_host_csr([domain])
        return issuer(csr_pem), key_pem

    fullchain, key_pem = await run_in_threadpool(_issue)

    for path, content, mode in (
        (settings.self_cert_path, fullchain, 0o644),
        (settings.self_cert_key_path, key_pem, 0o600),
    ):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)
        os.chmod(path, mode)

    leaf = x509.load_pem_x509_certificates(fullchain.encode())[0]
    async with session_scope() as session:
        session.add(
            Certificate(
                pem_chain=fullchain,
                domains=[domain],
                subject=leaf.subject.rfc4514_string(),
                serial=format(leaf.serial_number, "x"),
                not_after=leaf.not_valid_after_utc,
                key_storage="local_file",
                key_reference=settings.self_cert_key_path,
                issued_at=utcnow(),
            )
        )
        await session.commit()
    logger.info("Service certificate for %s issued to %s", domain, settings.self_cert_path)
    return True


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
