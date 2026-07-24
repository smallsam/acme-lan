"""Management REST API: certificates, stats, and realtime TLS health checks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..certlifecycle import (
    expiring_certificates,
    expiry_info,
    retire_certificate,
    unretire_certificate,
)
from ..config import get_settings
from ..db import get_session
from ..health import probe_tls
from ..models import Certificate, Order
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


class RetireRequest(BaseModel):
    reason: str | None = None


async def _certificate_view(cert: Certificate, session: AsyncSession) -> dict[str, Any]:
    warn_days = get_settings().expiry_warn_days
    # Domains come from the cert itself (host-issued) or the linked order (ACME client).
    domains = list(cert.domains) if cert.domains else []
    if not domains and cert.order_id:
        order = await session.get(Order, cert.order_id)
        domains = [i["value"] for i in order.identifiers] if order else []
    view = {
        "id": cert.id,
        "domains": domains,
        "primary_domain": domains[0] if domains else None,
        "serial": cert.serial,
        "subject": cert.subject,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "host_id": cert.host_id,
        "key_storage": cert.key_storage,
        "retired": cert.retired,
        "retired_reason": cert.retired_reason,
    }
    view.update(expiry_info(cert, warn_days))
    return view


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    orders = (await session.execute(select(Order))).scalars().all()
    certs = (await session.execute(select(Certificate))).scalars().all()
    by_status: dict[str, int] = {}
    for order in orders:
        by_status[order.status] = by_status.get(order.status, 0) + 1
    return {
        "orders_total": len(orders),
        "orders_by_status": by_status,
        "certificates_total": len(certs),
    }


@router.get("/certificates")
async def list_certificates(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    certs = (
        await session.execute(select(Certificate).order_by(Certificate.issued_at.desc()))
    ).scalars().all()
    return [await _certificate_view(c, session) for c in certs]


# Declared before /certificates/{id} so "expiring" isn't captured as an id.
@router.get("/certificates/expiring")
async def list_expiring(
    warn_days: int | None = None, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    days = warn_days if warn_days is not None else get_settings().expiry_warn_days
    certs = await expiring_certificates(session, days)
    return [await _certificate_view(c, session) for c in certs]


@router.post("/certificates/{certificate_id}/retire")
async def retire(
    certificate_id: str,
    body: RetireRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    await retire_certificate(session, cert, body.reason if body else None)
    return await _certificate_view(cert, session)


@router.post("/certificates/{certificate_id}/unretire")
async def unretire(
    certificate_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    await unretire_certificate(session, cert)
    return await _certificate_view(cert, session)


@router.get("/certificates/{certificate_id}")
async def get_certificate(
    certificate_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    view = await _certificate_view(cert, session)
    view["pem_chain"] = cert.pem_chain
    return view


@router.get("/certificates/{certificate_id}/key")
async def get_certificate_key(
    certificate_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Retrieve the stored private key for a cert (admin only; sensitive)."""
    from ..certstore.factory import get_cert_store

    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.key_storage == "none" or not cert.key_reference:
        raise HTTPException(status_code=404, detail="No private key stored for this certificate")
    store = get_cert_store()
    if store.name != cert.key_storage:
        raise HTTPException(
            status_code=409,
            detail=f"Key is in backend {cert.key_storage!r} but the active backend is "
            f"{store.name!r}",
        )
    bundle = await store.fetch(cert.key_reference)
    return {"key_storage": cert.key_storage, "key_pem": bundle.key_pem}


@router.get("/certificates/{certificate_id}/health")
async def certificate_health(
    certificate_id: str,
    port: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    domains = list(cert.domains) if cert.domains else []
    if not domains and cert.order_id:
        order = await session.get(Order, cert.order_id)
        domains = [i["value"] for i in order.identifiers] if order else []
    if not domains:
        raise HTTPException(status_code=400, detail="Certificate has no domain to probe")
    settings = get_settings()
    domain = domains[0].lstrip("*.")
    health = await probe_tls(
        domain, port or settings.health_default_port, timeout=settings.health_timeout
    )
    return health.to_dict()


class ProbeRequest(BaseModel):
    host: str
    port: int = 443
    server_name: str | None = None


@router.post("/health/probe")
async def probe(req: ProbeRequest) -> dict[str, Any]:
    settings = get_settings()
    health = await probe_tls(req.host, req.port, req.server_name, timeout=settings.health_timeout)
    return health.to_dict()


@router.get("/notifications/channels")
async def notification_channels() -> dict[str, Any]:
    from ..notifications import get_channels

    return {"channels": [c.name for c in get_channels()]}


@router.post("/notifications/test")
async def notification_test() -> dict[str, Any]:
    from ..notifications import Notification, get_channels, send_notification

    channels = get_channels()
    if not channels:
        raise HTTPException(400, "No notification channels configured")
    note = Notification(
        subject="[acme-lan] Test notification",
        message="This is a test notification from acme-lan.",
        data={"test": True},
    )
    sent = await send_notification(note, channels)
    return {"channels": [c.name for c in channels], "sent": sent}
