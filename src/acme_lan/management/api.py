"""Management REST API: certificates, stats, and realtime TLS health checks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..health import probe_tls
from ..models import Certificate, Order
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


async def _certificate_view(cert: Certificate, session: AsyncSession) -> dict[str, Any]:
    order = await session.get(Order, cert.order_id)
    domains = [i["value"] for i in order.identifiers] if order else []
    return {
        "id": cert.id,
        "domains": domains,
        "primary_domain": domains[0] if domains else None,
        "serial": cert.serial,
        "subject": cert.subject,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "order_status": order.status if order else None,
    }


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


@router.get("/certificates/{certificate_id}/health")
async def certificate_health(
    certificate_id: str,
    port: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
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
