"""Deploy plugin interface.

A plugin receives the freshly-issued certificate chain and its private key (acme-lan
generates the key itself for managed hosts, since the device can't run an ACME client)
and installs them onto the device, however that device expects it.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from ..credentials import DecryptedCredential
from ..models import ManagedHost


@dataclass
class DeployContext:
    host: ManagedHost
    fullchain_pem: str
    private_key_pem: str
    credential: DecryptedCredential | None
    config: dict[str, Any]


@dataclass
class DeployResult:
    ok: bool
    detail: str = ""


class DeployPlugin(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def deploy(self, ctx: DeployContext) -> DeployResult:
        """Install the certificate + key onto the host described by ``ctx``."""
