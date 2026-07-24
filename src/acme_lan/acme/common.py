"""Shared request/response plumbing for ACME endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import malformed
from .jws import VerifiedRequest, verify_jws
from .nonce import issue_nonce

# RFC 8555 requires JWS bodies to use this content type.
JOSE_CONTENT_TYPE = "application/jose+json"


async def read_verified(
    request: Request, session: AsyncSession, *, expected_url: str | None = None
) -> VerifiedRequest:
    """Read the request body and return a fully verified JWS."""
    ctype = request.headers.get("content-type", "").split(";")[0].strip()
    if ctype and ctype != JOSE_CONTENT_TYPE:
        raise malformed(f"Expected Content-Type {JOSE_CONTENT_TYPE}, got {ctype!r}")
    body = await request.body()
    return await verify_jws(request, body, session, expected_url=expected_url)


async def acme_json_response(
    content: dict[str, Any] | list[Any],
    *,
    status: int = 200,
    location: str | None = None,
    links: list[tuple[str, str]] | None = None,
) -> JSONResponse:
    """Build a JSON ACME response with a fresh Replay-Nonce (and optional Location/Link)."""
    headers = {"Replay-Nonce": await issue_nonce()}
    if location:
        headers["Location"] = location
    resp = JSONResponse(status_code=status, content=content, headers=headers)
    if links:
        _add_links(resp, links)
    return resp


async def acme_raw_response(
    content: bytes | str,
    *,
    media_type: str,
    status: int = 200,
    location: str | None = None,
    links: list[tuple[str, str]] | None = None,
) -> Response:
    """Build a non-JSON ACME response (e.g. a PEM certificate chain) with a Replay-Nonce."""
    headers = {"Replay-Nonce": await issue_nonce()}
    if location:
        headers["Location"] = location
    resp = Response(content=content, media_type=media_type, status_code=status, headers=headers)
    if links:
        _add_links(resp, links)
    return resp


def _add_links(resp: Response, links: list[tuple[str, str]]) -> None:
    values = [f'<{url}>;rel="{rel}"' for url, rel in links]
    resp.headers["Link"] = ", ".join(values)
