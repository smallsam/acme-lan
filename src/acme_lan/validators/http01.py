"""http-01 challenge validation (RFC 8555 §8.3).

This server acts as the ACME *server* for internal clients, so it is the party that
performs the http-01 check: it fetches ``/.well-known/acme-challenge/<token>`` from the
identifier and compares the body to the expected key authorization.

In split-horizon LANs the identifier may need to be reached at a different address than
public DNS suggests; ``settings.http01_resolver_overrides`` maps an identifier value to a
``host[:port]`` the validator should connect to instead (the ``Host`` header is preserved).
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import get_settings


@dataclass
class ValidationResult:
    ok: bool
    detail: str = ""


async def validate_http01(identifier: str, token: str, key_authorization: str) -> ValidationResult:
    settings = get_settings()
    override = settings.http01_resolver_overrides.get(identifier)
    connect_host = override or identifier
    host_header = identifier
    # Allow "host:port" overrides.
    url = f"http://{connect_host}/.well-known/acme-challenge/{token}"

    try:
        async with httpx.AsyncClient(timeout=settings.http01_timeout, follow_redirects=True) as c:
            resp = await c.get(url, headers={"Host": host_header, "Accept": "*/*"})
    except httpx.HTTPError as exc:
        return ValidationResult(False, f"Could not fetch challenge resource: {exc}")

    if resp.status_code != 200:
        return ValidationResult(False, f"Challenge resource returned HTTP {resp.status_code}")

    body = resp.text.strip()
    if body != key_authorization:
        return ValidationResult(
            False,
            "Challenge response did not match the expected key authorization",
        )
    return ValidationResult(True)
