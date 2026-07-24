"""Render database objects as RFC 8555 JSON resource representations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Account, Authorization, Challenge, Order
from .encoding import Urls


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def account_to_json(account: Account, urls: Urls) -> dict[str, Any]:
    return {
        "status": account.status,
        "contact": account.contact or [],
        "orders": urls.account_orders(account.id),
    }


def challenge_to_json(ch: Challenge, urls: Urls) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "type": ch.type,
        "url": urls.challenge(ch.id),
        "status": ch.status,
        "token": ch.token,
    }
    if ch.validated_at:
        doc["validated"] = iso(ch.validated_at)
    if ch.error:
        doc["error"] = ch.error
    return doc


async def authz_to_json(
    authz: Authorization, session: AsyncSession, urls: Urls
) -> dict[str, Any]:
    challenges = (
        await session.execute(select(Challenge).where(Challenge.authz_id == authz.id))
    ).scalars().all()
    doc: dict[str, Any] = {
        "status": authz.status,
        "expires": iso(authz.expires_at),
        "identifier": {"type": authz.identifier_type, "value": authz.identifier_value},
        "challenges": [challenge_to_json(c, urls) for c in challenges],
    }
    if authz.wildcard:
        doc["wildcard"] = True
    return doc


async def order_to_json(order: Order, session: AsyncSession, urls: Urls) -> dict[str, Any]:
    authzs = (
        await session.execute(select(Authorization).where(Authorization.order_id == order.id))
    ).scalars().all()
    doc: dict[str, Any] = {
        "status": order.status,
        "expires": iso(order.expires_at),
        "identifiers": order.identifiers,
        "authorizations": [urls.authorization(a.id) for a in authzs],
        "finalize": urls.finalize(order.id),
    }
    if order.not_before:
        doc["notBefore"] = order.not_before
    if order.not_after:
        doc["notAfter"] = order.not_after
    if order.certificate_id:
        doc["certificate"] = urls.certificate(order.certificate_id)
    if order.error:
        doc["error"] = order.error
    return doc
