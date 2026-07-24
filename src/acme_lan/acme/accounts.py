"""Account management endpoints (RFC 8555 §7.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Account
from .common import acme_json_response, read_verified
from .encoding import Urls, b64url_encode
from .errors import account_does_not_exist, malformed
from .serializers import account_to_json

router = APIRouter()


@router.post("/acme/new-account")
async def new_account(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    verified = await read_verified(request, session)
    if verified.account_id is not None:
        # A kid-signed request to new-account is not allowed; must use embedded jwk.
        raise malformed("newAccount must be signed with an embedded JWK, not a kid")

    payload = verified.payload or {}
    thumbprint = b64url_encode(verified.jwk.thumbprint())
    urls = Urls()

    existing = (
        await session.execute(select(Account).where(Account.key_thumbprint == thumbprint))
    ).scalar_one_or_none()

    if existing is not None:
        return await acme_json_response(
            account_to_json(existing, urls),
            status=200,
            location=urls.account(existing.id),
        )

    if payload.get("onlyReturnExisting"):
        raise account_does_not_exist()

    contact = payload.get("contact") or []
    if not isinstance(contact, list):
        raise malformed("contact must be an array of URLs")

    account = Account(
        key_thumbprint=thumbprint,
        jwk=verified.jwk_dict,
        contact=contact,
        terms_agreed=bool(payload.get("termsOfServiceAgreed")),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    return await acme_json_response(
        account_to_json(account, urls),
        status=201,
        location=urls.account(account.id),
    )


@router.post("/acme/acct/{account_id}")
async def account_detail(
    account_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    account = await session.get(Account, account_id)
    if account is None:
        raise account_does_not_exist()

    urls = Urls()
    # POST-as-GET returns the account; a payload may update contact info.
    if not verified.is_post_as_get:
        payload = verified.payload or {}
        if "contact" in payload:
            contact = payload["contact"]
            if not isinstance(contact, list):
                raise malformed("contact must be an array of URLs")
            account.contact = contact
        if payload.get("status") == "deactivated":
            account.status = "deactivated"
        session.add(account)
        await session.commit()
        await session.refresh(account)

    return await acme_json_response(
        account_to_json(account, urls), location=urls.account(account.id)
    )
