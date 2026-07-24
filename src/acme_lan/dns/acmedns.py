"""acme-dns DNS provider.

Delegates ``_acme-challenge.<domain>`` (via a one-time CNAME you create) to an
[acme-dns](https://github.com/joohoi/acme-dns) instance. This server then only holds the
acme-dns account credentials, never your primary DNS credentials. TXT records are set via
acme-dns's ``/update`` endpoint; acme-dns expires them itself, so removal is a no-op.
"""

from __future__ import annotations

import httpx

from .base import DnsProvider


class AcmeDnsProvider(DnsProvider):
    name = "acmedns"

    def __init__(
        self,
        api_url: str,
        username: str,
        password: str,
        subdomain: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not (api_url and username and password and subdomain):
            raise ValueError(
                "acme-dns requires api_url, username, password and subdomain to be configured"
            )
        self.api_url = api_url.rstrip("/")
        self._headers = {"X-Api-User": username, "X-Api-Key": password}
        self.subdomain = subdomain
        self._transport = transport

    def publish_txt(self, record_name: str, value: str) -> None:
        with httpx.Client(timeout=20, transport=self._transport) as client:
            resp = client.post(
                f"{self.api_url}/update",
                headers=self._headers,
                json={"subdomain": self.subdomain, "txt": value},
            )
            resp.raise_for_status()

    def remove_txt(self, record_name: str, value: str) -> None:
        # acme-dns keeps only the two most recent TXT values and expires them; nothing to do.
        return None
