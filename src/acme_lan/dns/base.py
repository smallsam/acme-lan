"""Abstract DNS provider interface.

A provider only needs to publish and later remove a single TXT record. Only this server
holds the credentials required to do so — that is the whole security premise of acme-lan.
"""

from __future__ import annotations

import abc


class DnsProvider(abc.ABC):
    """Publish/remove the ``_acme-challenge`` TXT records for DNS-01."""

    name: str = "base"

    @abc.abstractmethod
    def publish_txt(self, record_name: str, value: str) -> None:
        """Create a TXT record ``record_name`` with content ``value``.

        ``record_name`` is the fully-qualified record (e.g. ``_acme-challenge.db.example.net``).
        """

    @abc.abstractmethod
    def remove_txt(self, record_name: str, value: str) -> None:
        """Remove the TXT record previously published for ``record_name`` / ``value``."""

    # A-record publishing is optional and only needed for the edge http-01 upstream mode
    # when the identifier does not already resolve to the edge (e.g. in tests). Providers
    # that rely on pre-existing wildcard DNS leave ``supports_a`` False.
    supports_a: bool = False

    def publish_a(self, record_name: str, ip: str) -> None:  # pragma: no cover - optional
        raise NotImplementedError

    def remove_a(self, record_name: str, ip: str) -> None:  # pragma: no cover - optional
        raise NotImplementedError
