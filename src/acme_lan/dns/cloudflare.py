"""Cloudflare DNS provider (the primary real provider).

Requires an API token (``ACME_LAN_CLOUDFLARE_API_TOKEN``) scoped to *Zone.DNS:Edit* for the
zone(s) that hold your public records. The token lives only on this server.
"""

from __future__ import annotations

import httpx

from .base import DnsProvider

API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareError(RuntimeError):
    pass


class CloudflareProvider(DnsProvider):
    name = "cloudflare"

    def __init__(
        self,
        api_token: str,
        api_base: str = API_BASE,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_token:
            raise CloudflareError("Cloudflare API token is not configured")
        self.api_base = api_base.rstrip("/")
        self._transport = transport  # injectable for tests
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(headers=self._headers, timeout=20, transport=self._transport)

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success", False):
            raise CloudflareError(f"Cloudflare API error: {data.get('errors')}")
        return data

    def _find_zone_id(self, client: httpx.Client, record_name: str) -> str:
        """Find the zone whose name is the longest suffix of ``record_name``."""
        labels = record_name.rstrip(".").split(".")
        # Try example.net, then sub.example.net-style candidates from most to least specific
        # apex-ward: db.example.net -> example.net.
        candidates = [".".join(labels[i:]) for i in range(len(labels) - 1)]
        for candidate in candidates:
            data = self._check(client.get(f"{self.api_base}/zones", params={"name": candidate}))
            result = data.get("result") or []
            if result:
                return result[0]["id"]
        raise CloudflareError(f"No Cloudflare zone found for {record_name!r}")

    def publish_txt(self, record_name: str, value: str) -> None:
        with self._client() as client:
            zone_id = self._find_zone_id(client, record_name)
            self._check(
                client.post(
                    f"{self.api_base}/zones/{zone_id}/dns_records",
                    json={"type": "TXT", "name": record_name, "content": value, "ttl": 60},
                )
            )

    def remove_txt(self, record_name: str, value: str) -> None:
        with self._client() as client:
            zone_id = self._find_zone_id(client, record_name)
            data = self._check(
                client.get(
                    f"{self.api_base}/zones/{zone_id}/dns_records",
                    params={"type": "TXT", "name": record_name},
                )
            )
            for record in data.get("result") or []:
                # TXT content is returned quoted; match either form.
                if record.get("content", "").strip('"') == value:
                    self._check(
                        client.delete(
                            f"{self.api_base}/zones/{zone_id}/dns_records/{record['id']}"
                        )
                    )
