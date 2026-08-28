"""Optional bearer-token auth for the management API (single-tenant homelab)."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from ..config import get_settings


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    """Require the admin bearer token *iff* one is configured.

    When ``ACME_LAN_ADMIN_TOKEN`` is unset the API is open (trusted LAN / reverse-proxy
    auth). The ACME protocol endpoints are never affected by this.
    """
    token = get_settings().admin_token
    if not token:
        return
    expected = f"Bearer {token}"
    # Constant-time: a plain != leaks the token prefix through response timing.
    if not hmac.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")
