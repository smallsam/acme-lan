"""Certificate/key storage backend interface.

A backend persists a certificate chain and (optionally) its private key, returning an
opaque *reference* that can later fetch them back. Backends are pluggable so keys can live
in the local DB, Azure Key Vault, or HashiCorp Vault.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class StoredBundle:
    cert_pem: str
    key_pem: str | None


class CertStore(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def store(self, name: str, cert_pem: str, key_pem: str | None) -> str:
        """Persist the cert (+ optional key) under a logical ``name``; return a reference."""

    @abc.abstractmethod
    async def fetch(self, reference: str) -> StoredBundle:
        """Fetch a previously-stored bundle by reference."""

    @abc.abstractmethod
    async def delete(self, reference: str) -> None:
        """Delete a stored bundle (best-effort)."""
