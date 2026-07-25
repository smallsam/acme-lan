"""Select a remote secret provider from configuration."""

from __future__ import annotations

from ..config import Settings, get_settings
from .azure import AzureKeyVaultSecrets
from .base import SecretProvider
from .vault import VaultSecrets

SUPPORTED = ("azure_keyvault", "vault")


def get_secret_provider(name: str, settings: Settings | None = None) -> SecretProvider:
    settings = settings or get_settings()
    if name == "azure_keyvault":
        return AzureKeyVaultSecrets(settings.azure_keyvault_url)
    if name == "vault":
        return VaultSecrets(settings.vault_url, settings.vault_token, settings.vault_mount)
    raise ValueError(f"Unknown secret provider {name!r}; supported: {', '.join(SUPPORTED)}")
