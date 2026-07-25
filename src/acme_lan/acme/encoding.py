"""Encoding helpers and URL construction for the ACME server."""

from __future__ import annotations

import base64

from ..config import get_settings


def b64url_encode(data: bytes) -> str:
    """base64url without padding (RFC 8555 uses unpadded base64url everywhere)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    """Decode unpadded base64url."""
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


DEFAULT_PROFILE = "default"


def profile_prefix(profile: str) -> str:
    """The ACME path prefix for a profile: ``/acme`` for default, ``/acme/p/<name>`` else."""
    return "/acme" if profile == DEFAULT_PROFILE else f"/acme/p/{profile}"


def profile_from_request(request) -> str:
    """The listener profile a request landed on (default unless served under /acme/p/<name>)."""
    return request.path_params.get("profile", DEFAULT_PROFILE)


class Urls:
    """Builds the absolute URLs the ACME server advertises for a given listener profile.

    All URLs are derived from ``settings.external_url`` so the server works behind a
    reverse proxy as long as that value matches how clients reach it. Named profiles are
    served under ``/acme/p/<profile>/...`` so a single server can host several ACME
    listeners, each with its own upstream CA.
    """

    def __init__(self, base: str | None = None, profile: str = DEFAULT_PROFILE) -> None:
        self.base = (base or get_settings().external_url).rstrip("/")
        self.profile = profile
        self.prefix = profile_prefix(profile)

    def _u(self, path: str) -> str:
        return f"{self.base}{self.prefix}{path}"

    # Directory resources
    def directory(self) -> str:
        return self._u("/directory")

    def new_nonce(self) -> str:
        return self._u("/new-nonce")

    def new_account(self) -> str:
        return self._u("/new-account")

    def new_order(self) -> str:
        return self._u("/new-order")

    def revoke_cert(self) -> str:
        return self._u("/revoke-cert")

    def key_change(self) -> str:
        return self._u("/key-change")

    # Per-object resources
    def account(self, account_id: str) -> str:
        return self._u(f"/acct/{account_id}")

    def account_orders(self, account_id: str) -> str:
        return self._u(f"/acct/{account_id}/orders")

    def order(self, order_id: str) -> str:
        return self._u(f"/order/{order_id}")

    def finalize(self, order_id: str) -> str:
        return self._u(f"/order/{order_id}/finalize")

    def authorization(self, authz_id: str) -> str:
        return self._u(f"/authz/{authz_id}")

    def challenge(self, challenge_id: str) -> str:
        return self._u(f"/chall/{challenge_id}")

    def certificate(self, certificate_id: str) -> str:
        return self._u(f"/cert/{certificate_id}")
