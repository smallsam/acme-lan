"""Secret provider interface for fetching a single secret string by reference."""

from __future__ import annotations

import abc


class SecretProvider(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def get_secret(self, reference: str) -> str:
        """Return the secret value stored under ``reference``."""
