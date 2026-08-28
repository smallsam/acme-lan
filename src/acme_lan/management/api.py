"""Management REST API: certificates, stats, and realtime TLS health checks."""

from __future__ import annotations

from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..certaudit import DeploymentAudit, IssuedCert, audit_deployment
from ..certlifecycle import (
    expiring_certificates,
    expiry_info,
    retire_certificate,
    unretire_certificate,
)
from ..config import get_settings
from ..db import get_session
from ..health import probe_tls
from ..models import Certificate, HealthCheckPort, ManagedHost, Order, utcnow
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


class RetireRequest(BaseModel):
    reason: str | None = None


async def _certificate_domains(cert: Certificate, session: AsyncSession) -> list[str]:
    # Domains come from the cert itself (host-issued) or the linked order (ACME client).
    domains = list(cert.domains) if cert.domains else []
    if not domains and cert.order_id:
        order = await session.get(Order, cert.order_id)
        domains = [i["value"] for i in order.identifiers] if order else []
    return domains


async def _certificate_view(cert: Certificate, session: AsyncSession) -> dict[str, Any]:
    warn_days = get_settings().expiry_warn_days
    domains = await _certificate_domains(cert, session)
    check_port = None
    if domains:
        override = await session.get(HealthCheckPort, domains[0].lstrip("*."))
        check_port = override.port if override else None
    view = {
        "id": cert.id,
        "domains": domains,
        "primary_domain": domains[0] if domains else None,
        "serial": cert.serial,
        "subject": cert.subject,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "host_id": cert.host_id,
        "host_name": None,
        "check_port": check_port,
        "key_storage": cert.key_storage,
        "retired": cert.retired,
        "retired_reason": cert.retired_reason,
    }
    if cert.host_id:
        host = await session.get(ManagedHost, cert.host_id)
        view["host_name"] = host.name if host else None
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


CERT_SORTS = {
    "issued_at": Certificate.issued_at,
    "not_after": Certificate.not_after,
    "subject": Certificate.subject,
}


def _page(items: list[dict[str, Any]], limit: int, offset: int) -> dict[str, Any]:
    return {
        "items": items[offset : offset + limit] if limit else items[offset:],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/certificates")
async def list_certificates(
    search: str = "",
    sort: str = "issued_at",
    order: str = "desc",
    limit: int = Query(default=25, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_superseded: bool = False,
    include_retired: bool = True,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """List certificates, newest first.

    A certificate is *superseded* when a newer, non-retired certificate exists for the same
    primary domain — a renewal, in other words. Those are hidden by default so the list
    shows one row per name instead of the full issuance history.
    """
    column = CERT_SORTS.get(sort, Certificate.issued_at)
    statement = select(Certificate).order_by(
        column.asc() if order == "asc" else column.desc()
    )
    certs = (await session.execute(statement)).scalars().all()

    views = [await _certificate_view(c, session) for c in certs]
    # Newest issuance per primary domain, ignoring retired rows (deliberately out of service).
    newest: dict[str, str] = {}
    for view in sorted(views, key=lambda v: v["issued_at"] or "", reverse=True):
        domain = (view["primary_domain"] or "").lower()
        if domain and not view["retired"] and domain not in newest:
            newest[domain] = view["id"]
    for view in views:
        domain = (view["primary_domain"] or "").lower()
        view["superseded"] = bool(
            domain and not view["retired"] and newest.get(domain) not in (None, view["id"])
        )

    if not include_superseded:
        views = [v for v in views if not v["superseded"]]
    if not include_retired:
        views = [v for v in views if not v["retired"]]
    if search:
        needle = search.strip().lower()
        views = [
            v
            for v in views
            if needle in " ".join(
                str(part).lower()
                for part in (
                    *(v["domains"] or []),
                    v["subject"] or "",
                    v["serial"] or "",
                    v["host_name"] or "",
                )
            )
        ]
    return _page(views, limit, offset)


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


def _leaf_details(pem_chain: str) -> dict[str, Any] | None:
    """Parse the leaf certificate of a PEM chain into display fields (None if unparseable)."""
    try:
        leaf = x509.load_pem_x509_certificates(pem_chain.encode())[0]
    except Exception:  # noqa: BLE001 - seeded/legacy rows may hold junk PEM
        return None

    def _attr(name: x509.Name, oid) -> str | None:
        attrs = name.get_attributes_for_oid(oid)
        return attrs[0].value if attrs else None

    try:
        san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        san_dns = list(san.get_values_for_type(x509.DNSName))
        san_email = list(san.get_values_for_type(x509.RFC822Name))
    except x509.ExtensionNotFound:
        san_dns, san_email = [], []
    return {
        "subject": leaf.subject.rfc4514_string(),
        "issuer": leaf.issuer.rfc4514_string(),
        "common_name": _attr(leaf.subject, NameOID.COMMON_NAME),
        "organization": _attr(leaf.subject, NameOID.ORGANIZATION_NAME),
        "email": (
            _attr(leaf.subject, NameOID.EMAIL_ADDRESS)
            or (san_email[0] if san_email else None)
        ),
        "serial": format(leaf.serial_number, "x"),
        "not_before": leaf.not_valid_before_utc.isoformat(),
        "not_after": leaf.not_valid_after_utc.isoformat(),
        "sans": san_dns,
    }


@router.get("/certificates/{certificate_id}")
async def get_certificate(
    certificate_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    view = await _certificate_view(cert, session)
    view["pem_chain"] = cert.pem_chain
    view["details"] = _leaf_details(cert.pem_chain)
    return view


@router.get("/certificates/{certificate_id}/download")
async def download_certificate(
    certificate_id: str,
    kind: str = "chain",
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download the certificate as a PEM attachment.

    ``kind=leaf`` returns only the end-entity certificate; ``kind=chain`` (default)
    returns the full chain as issued.
    """
    if kind not in ("leaf", "chain"):
        raise HTTPException(status_code=400, detail="kind must be 'leaf' or 'chain'")
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    domains = await _certificate_domains(cert, session)
    name = (domains[0].lstrip("*.") if domains else cert.id) or cert.id

    body = cert.pem_chain
    suffix = "chain"
    if kind == "leaf":
        try:
            leaf = x509.load_pem_x509_certificates(cert.pem_chain.encode())[0]
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422, detail="Stored PEM could not be parsed to extract the leaf"
            ) from exc
        body = leaf.public_bytes(serialization.Encoding.PEM).decode()
        suffix = "cert"
    return Response(
        content=body,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f'attachment; filename="{name}-{suffix}.pem"'},
    )


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
    domains = await _certificate_domains(cert, session)
    if not domains:
        raise HTTPException(status_code=400, detail="Certificate has no domain to probe")
    settings = get_settings()
    domain = domains[0].lstrip("*.")
    # In split-horizon LANs the cert's domain may need probing at a different address.
    override = settings.health_resolver_overrides.get(domain)
    host, _, override_port = (override or domain).partition(":")
    host_port: int | None = None
    if override is None and cert.host_id:
        # A certificate acme-lan pushed to a managed device: probe the device's own
        # address. The certificate's name frequently has no LAN A record at all, so
        # resolving it would just fail.
        managed = await session.get(ManagedHost, cert.host_id)
        if managed and managed.address:
            host = managed.address
            host_port = managed.port
    # Port precedence: explicit query param > stored per-hostname check port >
    # resolver-override port > managed host port > default.
    stored = await session.get(HealthCheckPort, domain)
    probe_port = (
        port
        or (stored.port if stored else None)
        or (int(override_port) if override_port else None)
        or host_port
        or settings.health_default_port
    )
    health = await probe_tls(
        host, probe_port, server_name=domain, timeout=settings.health_timeout
    )
    result = health.to_dict()
    # Trust/expiry (above) describe the certificate itself; the audit below is a separate
    # question — is this the certificate we issued, and is renewal keeping up?
    result["deployment"] = (
        await _audit_deployment(
            session, domain, health.serial, health.issuer, settings, this_serial=cert.serial
        )
    ).to_dict()
    return result


async def _audit_deployment(
    session: AsyncSession,
    domain: str,
    served_serial,
    served_issuer,
    settings,
    *,
    this_serial: str | None = None,
) -> DeploymentAudit:
    """Gather what acme-lan issued for ``domain`` and compare it with what's served."""
    rows = (await session.execute(select(Certificate))).scalars().all()
    issued: list[IssuedCert] = []
    for row in rows:
        row_domains = [d.lstrip("*.") for d in await _certificate_domains(row, session)]
        if domain not in row_domains:
            continue
        details = _leaf_details(row.pem_chain)
        issued.append(
            IssuedCert(
                serial=row.serial or (details or {}).get("serial"),
                not_after=row.not_after,
                issued_at=row.issued_at,
                issuer=(details or {}).get("issuer"),
                retired=row.retired,
            )
        )
    return audit_deployment(
        served_serial=served_serial,
        served_issuer=served_issuer,
        issued=issued,
        renew_before_days=settings.renew_before_days,
        this_serial=this_serial,
    )


class CheckPortRequest(BaseModel):
    # None clears the override so the probe falls back to the default port.
    port: int | None = Field(default=None, ge=1, le=65535)


@router.put("/certificates/{certificate_id}/check-port")
async def set_check_port(
    certificate_id: str,
    body: CheckPortRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Set (or clear) the TLS health-check port for this certificate's hostname.

    Stored keyed by hostname, so it carries over to renewals of the same domain.
    """
    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    domains = await _certificate_domains(cert, session)
    if not domains:
        raise HTTPException(status_code=400, detail="Certificate has no domain")
    domain = domains[0].lstrip("*.")
    existing = await session.get(HealthCheckPort, domain)
    if body.port is None:
        if existing:
            await session.delete(existing)
    elif existing:
        existing.port = body.port
        existing.updated_at = utcnow()
        session.add(existing)
    else:
        session.add(HealthCheckPort(domain=domain, port=body.port))
    await session.commit()
    return await _certificate_view(cert, session)


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
