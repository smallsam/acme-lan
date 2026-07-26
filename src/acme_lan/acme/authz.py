"""Authorization and challenge endpoints (RFC 8555 §7.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Authorization, AuthzStatus, Challenge, ChallengeStatus, Order, utcnow
from ..validators.http01 import validate_http01
from ..validators.tlsalpn01 import validate_tlsalpn01
from .common import acme_json_response, read_verified
from .encoding import Urls, profile_from_request
from .errors import malformed, unauthorized
from .serializers import authz_to_json, challenge_to_json

router = APIRouter()


async def _load_owned_authz(authz_id: str, account_id: str, session: AsyncSession):
    authz = await session.get(Authorization, authz_id)
    if authz is None:
        raise unauthorized("Unknown authorization")
    order = await session.get(Order, authz.order_id)
    if order is None or order.account_id != account_id:
        raise unauthorized("Authorization does not belong to this account")
    return authz, order


@router.post("/authz/{authz_id}")
async def authorization_detail(
    authz_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    if verified.account is None:
        raise unauthorized("Request must be signed with an account key identifier (kid)")
    authz, _ = await _load_owned_authz(authz_id, verified.account.id, session)
    urls = Urls(profile=profile_from_request(request))
    return await acme_json_response(await authz_to_json(authz, session, urls))


@router.post("/chall/{challenge_id}")
async def respond_challenge(
    challenge_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> Response:
    verified = await read_verified(request, session)
    if verified.account is None:
        raise unauthorized("Request must be signed with an account key identifier (kid)")

    challenge = await session.get(Challenge, challenge_id)
    if challenge is None:
        raise unauthorized("Unknown challenge")
    authz, _ = await _load_owned_authz(challenge.authz_id, verified.account.id, session)

    urls = Urls(profile=profile_from_request(request))
    # Already resolved — just return current state (clients may re-POST while polling).
    if challenge.status in (ChallengeStatus.VALID, ChallengeStatus.INVALID):
        return await acme_json_response(
            challenge_to_json(challenge, urls),
            links=[(urls.authorization(authz.id), "up")],
        )

    key_authorization = f"{challenge.token}.{verified.thumbprint_b64()}"

    if challenge.type == "http-01":
        result = await validate_http01(authz.identifier_value, challenge.token, key_authorization)
    elif challenge.type == "tls-alpn-01":
        result = await validate_tlsalpn01(authz.identifier_value, key_authorization)
    else:
        raise malformed(f"Challenge type {challenge.type!r} is not supported for validation yet")

    if result.ok:
        challenge.status = ChallengeStatus.VALID
        challenge.validated_at = utcnow()
        authz.status = AuthzStatus.VALID
    else:
        challenge.status = ChallengeStatus.INVALID
        challenge.error = {
            "type": "urn:ietf:params:acme:error:unauthorized",
            "detail": result.detail,
        }
        authz.status = AuthzStatus.INVALID

    session.add(challenge)
    session.add(authz)
    await session.commit()
    await session.refresh(challenge)

    return await acme_json_response(
        challenge_to_json(challenge, urls),
        links=[(urls.authorization(authz.id), "up")],
    )
