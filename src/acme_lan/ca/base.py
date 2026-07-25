"""CA handler interface.

Mirrors acme2certifier's ``ca_handler`` contract: given a CSR, enroll a certificate from
a (typically private) CA that doesn't speak ACME. This lets a named acme-lan listener issue
from an internal CA — useful for e.g. pushing WiFi certificates that must chain to a private
root. Drop-in acme2certifier handler modules can be adapted to this interface.
"""

from __future__ import annotations

import abc


class CaHandler(abc.ABC):
    name: str = "base"

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}

    @abc.abstractmethod
    def enroll(self, csr_pem: str) -> str:
        """Issue a certificate for the CSR; return the full chain (PEM)."""

    def revoke(self, cert_pem: str, reason: int | None = None) -> None:  # pragma: no cover
        raise NotImplementedError(f"{self.name} handler does not support revocation")
