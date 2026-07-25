"""Directory and newNonce endpoints (RFC 8555 §7.1.1, §7.2)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .encoding import Urls, profile_from_request
from .nonce import issue_nonce

router = APIRouter()


@router.get("/directory")
async def directory(request: Request) -> dict:
    urls = Urls(profile=profile_from_request(request))
    return {
        "newNonce": urls.new_nonce(),
        "newAccount": urls.new_account(),
        "newOrder": urls.new_order(),
        "revokeCert": urls.revoke_cert(),
        "keyChange": urls.key_change(),
        "meta": {
            "externalAccountRequired": False,
            "website": "https://github.com/smallsam/acme-lan",
        },
    }


@router.head("/new-nonce")
async def new_nonce_head() -> Response:
    nonce = await issue_nonce()
    return Response(status_code=200, headers={"Replay-Nonce": nonce, "Cache-Control": "no-store"})


@router.get("/new-nonce")
async def new_nonce_get() -> Response:
    nonce = await issue_nonce()
    return Response(status_code=204, headers={"Replay-Nonce": nonce, "Cache-Control": "no-store"})
