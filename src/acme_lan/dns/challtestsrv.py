"""DNS provider backed by pebble-challtestsrv's management API (test only).

pebble-challtestsrv is the mock DNS/challenge server that Pebble queries during
validation. Its management API lets us set and clear TXT records so Pebble's DNS-01
validation sees what we publish. See https://github.com/letsencrypt/pebble.
"""

from __future__ import annotations

import httpx

from .base import DnsProvider


class ChallTestSrvProvider(DnsProvider):
    name = "challtestsrv"
    supports_a = True

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _fqdn(record_name: str) -> str:
        return record_name if record_name.endswith(".") else record_name + "."

    def publish_txt(self, record_name: str, value: str) -> None:
        resp = httpx.post(
            f"{self.base_url}/set-txt",
            json={"host": self._fqdn(record_name), "value": value},
            timeout=10,
        )
        resp.raise_for_status()

    def remove_txt(self, record_name: str, value: str) -> None:
        resp = httpx.post(
            f"{self.base_url}/clear-txt",
            json={"host": self._fqdn(record_name)},
            timeout=10,
        )
        resp.raise_for_status()

    def publish_a(self, record_name: str, ip: str) -> None:
        resp = httpx.post(
            f"{self.base_url}/add-a",
            json={"host": self._fqdn(record_name), "addresses": [ip]},
            timeout=10,
        )
        resp.raise_for_status()

    def remove_a(self, record_name: str, ip: str) -> None:
        resp = httpx.post(
            f"{self.base_url}/clear-a",
            json={"host": self._fqdn(record_name)},
            timeout=10,
        )
        resp.raise_for_status()
