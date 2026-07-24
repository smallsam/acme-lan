"""Select a certificate/key storage backend from configuration."""

from __future__ import annotations

from ..config import Settings, get_settings
from .azure import AzureKeyVaultStore
from .base import CertStore
from .local import LocalCertStore
from .vault import VaultCertStore


def get_cert_store(settings: Settings | None = None) -> CertStore:
    settings = settings or get_settings()
    backend = settings.cert_store_backend.lower()
    if backend == "local":
        return LocalCertStore()
    if backend == "azure_keyvault":
        return AzureKeyVaultStore(settings.azure_keyvault_url)
    if backend == "vault":
        return VaultCertStore(
            settings.vault_url,
            settings.vault_token,
            settings.vault_mount,
            settings.vault_path_prefix,
        )
    raise ValueError(f"Unknown cert store backend {settings.cert_store_backend!r}")
