"""Certificate download and revocation endpoints (RFC 8555 §7.4.2, §7.6)."""

from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Certificate, Order
from .common import acme_json_response, acme_raw_response, read_verified
from .encoding import b64url_decode
from .errors import AcmeError, malformed, unauthorized

router = APIRouter()

PEM_CHAIN_MEDIA_TYPE = "application/pem-certificate-chain"


@router.post("/acme/cert/{certificate_id}")
async def download_certificate(
    certificate_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    if verified.account is None:
        raise unauthorized("Request must be signed with an account key identifier (kid)")

    cert = await session.get(Certificate, certificate_id)
    if cert is None:
        raise unauthorized("Unknown certificate")
    order = await session.get(Order, cert.order_id)
    if order is None or order.account_id != verified.account.id:
        raise unauthorized("Certificate does not belong to this account")

    return await acme_raw_response(cert.pem_chain, media_type=PEM_CHAIN_MEDIA_TYPE)


@router.post("/acme/revoke-cert")
async def revoke_certificate(
    request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    payload = verified.payload or {}
    cert_b64 = payload.get("certificate")
    if not cert_b64:
        raise malformed("revoke request must contain a base64url DER 'certificate'")
    try:
        cert_der = b64url_decode(cert_b64)
        cert = x509.load_der_x509_certificate(cert_der)
    except Exception as exc:  # noqa: BLE001
        raise malformed("Could not parse certificate") from exc

    reason = payload.get("reason")
    cert_pem = cert.public_bytes(Encoding.PEM).decode("ascii")

    # Forward the revocation to the upstream CA that actually issued the certificate.
    from ..upstream.fulfil import revoke_certificate as upstream_revoke

    try:
        await run_in_threadpool(upstream_revoke, cert_pem, reason)
    except Exception as exc:  # noqa: BLE001
        raise AcmeError("serverInternal", f"Upstream revocation failed: {exc}", status=500) from exc

    return await acme_json_response({}, status=200)
