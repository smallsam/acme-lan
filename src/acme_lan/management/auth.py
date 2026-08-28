"""Authentication for the dashboard and management API.

Three ways to be authorised, in the order they're checked:

1. the admin bearer token (``ACME_LAN_ADMIN_TOKEN``), for scripts and back-compatibility;
2. a session cookie from a local or OIDC login;
3. nothing at all — allowed only while ``auth_required`` is false, which keeps the
   trusted-LAN / reverse-proxy-auth deployment working exactly as before.

The ACME protocol endpoints are never gated by any of this; RFC 8555 clients authenticate
with their own account keys.
"""

from __future__ import annotations

import hmac

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import User
from ..users import SESSION_COOKIE, resolve_session


async def require_admin(
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Authorise a management request, raising 401 when it can't be."""
    settings = get_settings()

    token = settings.admin_token
    if token and authorization:
        # Constant-time: a plain != leaks the token prefix through response timing.
        if hmac.compare_digest(authorization, f"Bearer {token}"):
            return None
        raise HTTPException(status_code=401, detail="Invalid admin token")

    user = await resolve_session(session, session_cookie)
    if user is not None:
        return user

    if settings.auth_required:
        raise HTTPException(status_code=401, detail="Authentication required")
    if token:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
    return None


async def require_user(user: User | None = Depends(require_admin)) -> User:
    """For endpoints that need a real user (e.g. changing your own password)."""
    if user is None:
        raise HTTPException(status_code=401, detail="This action requires a logged-in user")
    return user
