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
    # None in CSR-from-device mode, where the key stays on the device.
    private_key_pem: str | None
    credential: DecryptedCredential | None
    config: dict[str, Any]


@dataclass
class DeployResult:
    ok: bool
    detail: str = ""


class DeployPlugin(abc.ABC):
    name: str = "base"
    # Whether this plugin can retrieve a CSR from the device (enables the preferred,
    # key-never-leaves-the-device mode).
    supports_csr_retrieval: bool = False

    @abc.abstractmethod
    def deploy(self, ctx: DeployContext) -> DeployResult:
        """Mode 2: install the certificate *and* private key onto the host."""

    def fetch_csr(self, ctx: DeployContext) -> str:
        """Mode 1: retrieve a CSR (PEM) generated on the device. Key stays on the device."""
        raise NotImplementedError(f"{self.name} plugin cannot retrieve a CSR from the device")

    def install_cert(self, ctx: DeployContext) -> DeployResult:
        """Mode 1: install only the signed certificate (no key) onto the host."""
        raise NotImplementedError(f"{self.name} plugin cannot install a cert without a key")
