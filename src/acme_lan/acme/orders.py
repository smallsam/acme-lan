"""Order lifecycle endpoints: newOrder, order polling, finalize (RFC 8555 §7.4)."""

from __future__ import annotations

import secrets
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtensionOID
from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import (
    Authorization,
    AuthzStatus,
    Certificate,
    Challenge,
    Order,
    OrderStatus,
    utcnow,
)
from .common import acme_json_response, read_verified
from .encoding import Urls, b64url_decode
from .errors import AcmeError, malformed, order_not_ready, server_internal, unauthorized
from .serializers import order_to_json

router = APIRouter()

ORDER_TTL = timedelta(days=7)


def _new_token() -> str:
    return secrets.token_urlsafe(32)


async def _authorize_account(verified, session: AsyncSession):
    if verified.account is None:
        raise unauthorized("Request must be signed with an account key identifier (kid)")
    return verified.account


async def recompute_order_status(order: Order, session: AsyncSession) -> None:
    """Derive order status from its authorizations, without downgrading terminal states."""
    if order.status in (OrderStatus.VALID, OrderStatus.INVALID, OrderStatus.PROCESSING):
        return
    authzs = (
        await session.execute(select(Authorization).where(Authorization.order_id == order.id))
    ).scalars().all()
    statuses = [a.status for a in authzs]
    if any(s == AuthzStatus.INVALID for s in statuses):
        order.status = OrderStatus.INVALID
    elif statuses and all(s == AuthzStatus.VALID for s in statuses):
        order.status = OrderStatus.READY
    else:
        order.status = OrderStatus.PENDING
    session.add(order)


@router.post("/acme/new-order")
async def new_order(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    verified = await read_verified(request, session)
    account = await _authorize_account(verified, session)
    payload = verified.payload or {}

    identifiers = payload.get("identifiers")
    if not isinstance(identifiers, list) or not identifiers:
        raise malformed("Order must contain a non-empty 'identifiers' array")

    normalized: list[dict[str, str]] = []
    for ident in identifiers:
        if not isinstance(ident, dict) or ident.get("type") != "dns" or not ident.get("value"):
            raise AcmeError("unsupportedIdentifier", f"Unsupported identifier {ident!r}")
        normalized.append({"type": "dns", "value": ident["value"]})

    expires = utcnow() + ORDER_TTL
    order = Order(
        account_id=account.id,
        status=OrderStatus.PENDING,
        identifiers=normalized,
        not_before=payload.get("notBefore"),
        not_after=payload.get("notAfter"),
        expires_at=expires,
    )
    session.add(order)
    await session.flush()  # assign order.id

    for ident in normalized:
        value = ident["value"]
        wildcard = value.startswith("*.")
        base = value[2:] if wildcard else value
        authz = Authorization(
            order_id=order.id,
            identifier_type="dns",
            identifier_value=base,
            wildcard=wildcard,
            status=AuthzStatus.PENDING,
            expires_at=expires,
        )
        session.add(authz)
        await session.flush()
        # Wildcards require dns-01; everything else is offered http-01 for MVP.
        challenge_type = "dns-01" if wildcard else "http-01"
        session.add(
            Challenge(authz_id=authz.id, type=challenge_type, token=_new_token())
        )

    await session.commit()
    await session.refresh(order)

    urls = Urls()
    return await acme_json_response(
        await order_to_json(order, session, urls),
        status=201,
        location=urls.order(order.id),
    )


@router.post("/acme/order/{order_id}")
async def order_detail(
    order_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    account = await _authorize_account(verified, session)
    order = await session.get(Order, order_id)
    if order is None or order.account_id != account.id:
        raise unauthorized("Unknown order")

    await recompute_order_status(order, session)
    await session.commit()
    await session.refresh(order)

    urls = Urls()
    return await acme_json_response(
        await order_to_json(order, session, urls), location=urls.order(order.id)
    )


def _csr_dns_names(csr: x509.CertificateSigningRequest) -> set[str]:
    try:
        san = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        return set(san.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        return set()


@router.post("/acme/order/{order_id}/finalize")
async def finalize_order(
    order_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    account = await _authorize_account(verified, session)
    order = await session.get(Order, order_id)
    if order is None or order.account_id != account.id:
        raise unauthorized("Unknown order")

    await recompute_order_status(order, session)
    if order.status != OrderStatus.READY:
        await session.commit()
        raise order_not_ready(f"Order status is {order.status!r}, expected 'ready'")

    payload = verified.payload or {}
    csr_b64 = payload.get("csr")
    if not csr_b64:
        raise malformed("finalize request must contain a base64url DER 'csr'")
    try:
        csr_der = b64url_decode(csr_b64)
        csr = x509.load_der_x509_csr(csr_der)
    except Exception as exc:  # noqa: BLE001
        raise AcmeError("badCSR", "Could not parse CSR") from exc

    order_names = {i["value"] for i in order.identifiers}
    csr_names = _csr_dns_names(csr)
    if csr_names != order_names:
        raise AcmeError(
            "badCSR",
            f"CSR SANs {sorted(csr_names)} do not match order identifiers {sorted(order_names)}",
        )

    csr_pem = csr.public_bytes(Encoding.PEM).decode("ascii")

    order.status = OrderStatus.PROCESSING
    session.add(order)
    await session.commit()

    # Proxy step: obtain a real certificate from the upstream CA via DNS-01.
    from ..upstream.fulfil import fulfil_order

    try:
        fullchain_pem = await run_in_threadpool(fulfil_order, csr_pem)
    except Exception as exc:  # noqa: BLE001
        order.status = OrderStatus.INVALID
        order.error = {
            "type": "urn:ietf:params:acme:error:serverInternal",
            "detail": f"Upstream issuance failed: {exc}",
        }
        session.add(order)
        await session.commit()
        raise server_internal(f"Upstream issuance failed: {exc}") from exc

    leaf = x509.load_pem_x509_certificates(fullchain_pem.encode())[0]
    cert = Certificate(
        order_id=order.id,
        pem_chain=fullchain_pem,
        serial=format(leaf.serial_number, "x"),
        subject=leaf.subject.rfc4514_string(),
        not_after=leaf.not_valid_after_utc,
    )
    session.add(cert)
    await session.flush()
    order.certificate_id = cert.id
    order.status = OrderStatus.VALID
    session.add(order)
    await session.commit()
    await session.refresh(order)

    urls = Urls()
    return await acme_json_response(
        await order_to_json(order, session, urls), location=urls.order(order.id)
    )
