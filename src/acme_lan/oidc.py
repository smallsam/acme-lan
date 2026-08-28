"""OIDC authorization-code login with PKCE.

Deliberately small: discovery, an authorize URL, and a code exchange. Entra ID needs only a
directory (tenant) ID — :attr:`Settings.oidc_discovery` builds its discovery URL — so the
"easy Entra flow" is one field plus the app registration's client ID and secret.

**On ID token validation:** the token is fetched by this server directly from the provider's
token endpoint over TLS, authenticating with the client secret. OpenID Connect Core
§3.1.3.7 permits skipping the signature check in exactly that case, so this module validates
the claims that still matter (issuer, audience, expiry, nonce) instead of carrying a JWT/JWKS
dependency. The code never trusts an ID token that arrived any other way.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

DISCOVERY_TIMEOUT = 10.0


class OidcError(RuntimeError):
    pass


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode a JWT payload without verifying its signature (see the module docstring)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise OidcError("malformed ID token")
    try:
        return json.loads(_b64url_decode(parts[1]))
    except (ValueError, TypeError) as exc:
        raise OidcError("could not decode the ID token payload") from exc


def make_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for S256 PKCE."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


async def fetch_discovery(discovery_url: str) -> dict[str, Any]:
    if not discovery_url:
        raise OidcError("no OIDC discovery URL configured")
    async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT) as client:
        response = await client.get(discovery_url)
    if response.status_code >= 400:
        raise OidcError(f"discovery failed ({response.status_code}) for {discovery_url}")
    try:
        document = response.json()
    except ValueError as exc:
        raise OidcError("discovery document was not JSON") from exc
    for required in ("authorization_endpoint", "token_endpoint", "issuer"):
        if not document.get(required):
            raise OidcError(f"discovery document is missing {required}")
    return document


def authorize_url(
    document: dict[str, Any],
    *,
    client_id: str,
    redirect_uri: str,
    scopes: str,
    state: str,
    nonce: str,
    code_challenge: str,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes or "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{document['authorization_endpoint']}?{urlencode(params)}"


async def exchange_code(
    document: dict[str, Any],
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT) as client:
        response = await client.post(document["token_endpoint"], data=data)
    if response.status_code >= 400:
        raise OidcError(f"token exchange failed ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    if not payload.get("id_token"):
        raise OidcError("token response contained no id_token")
    return payload


def validate_claims(
    claims: dict[str, Any], *, issuer: str, client_id: str, nonce: str, now: int
) -> None:
    """Check the claims that still guard us once the transport is trusted."""
    token_issuer = claims.get("iss", "")
    if issuer and token_issuer != issuer:
        # Entra's multi-tenant issuer embeds the tenant id; compare with that substituted.
        expected = issuer.replace("{tenantid}", str(claims.get("tid", "")))
        if token_issuer != expected:
            raise OidcError(f"unexpected issuer {token_issuer!r}")
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if client_id not in [a for a in audiences if a]:
        raise OidcError("ID token audience does not match the configured client ID")
    expiry = claims.get("exp")
    if not isinstance(expiry, int) or expiry <= now:
        raise OidcError("ID token has expired")
    if nonce and claims.get("nonce") != nonce:
        raise OidcError("ID token nonce did not match the login request")


def claim_identity(claims: dict[str, Any]) -> tuple[str, str, str]:
    """Return (subject, email, display name) from ID token claims."""
    subject = str(claims.get("sub") or "")
    email = str(
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or ""
    )
    name = str(claims.get("name") or email or subject)
    return subject, email, name
