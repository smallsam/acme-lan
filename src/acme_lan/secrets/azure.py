"""Azure Key Vault secret provider (device credentials)."""

from __future__ import annotations

from .base import SecretProvider


class AzureKeyVaultSecrets(SecretProvider):
    name = "azure_keyvault"

    def __init__(self, vault_url: str, client=None) -> None:
        self._vault_url = vault_url
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "Azure Key Vault provider requires azure-identity and "
                    "azure-keyvault-secrets (pip install .[storage])"
                ) from exc
            self._client = SecretClient(
                vault_url=self._vault_url, credential=DefaultAzureCredential()
            )
        return self._client

    def get_secret(self, reference: str) -> str:
        return self._get_client().get_secret(reference).value
