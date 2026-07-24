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


class Urls:
    """Builds the absolute URLs the ACME server advertises.

    All URLs are derived from ``settings.external_url`` so the server works behind a
    reverse proxy as long as that value matches how clients reach it.
    """

    def __init__(self, base: str | None = None) -> None:
        self.base = (base or get_settings().external_url).rstrip("/")

    def _u(self, path: str) -> str:
        return f"{self.base}{path}"

    # Directory resources
    def directory(self) -> str:
        return self._u("/acme/directory")

    def new_nonce(self) -> str:
        return self._u("/acme/new-nonce")

    def new_account(self) -> str:
        return self._u("/acme/new-account")

    def new_order(self) -> str:
        return self._u("/acme/new-order")

    def revoke_cert(self) -> str:
        return self._u("/acme/revoke-cert")

    def key_change(self) -> str:
        return self._u("/acme/key-change")

    # Per-object resources
    def account(self, account_id: str) -> str:
        return self._u(f"/acme/acct/{account_id}")

    def account_orders(self, account_id: str) -> str:
        return self._u(f"/acme/acct/{account_id}/orders")

    def order(self, order_id: str) -> str:
        return self._u(f"/acme/order/{order_id}")

    def finalize(self, order_id: str) -> str:
        return self._u(f"/acme/order/{order_id}/finalize")

    def authorization(self, authz_id: str) -> str:
        return self._u(f"/acme/authz/{authz_id}")

    def challenge(self, challenge_id: str) -> str:
        return self._u(f"/acme/chall/{challenge_id}")

    def certificate(self, certificate_id: str) -> str:
        return self._u(f"/acme/cert/{certificate_id}")
