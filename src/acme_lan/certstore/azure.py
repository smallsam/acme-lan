"""Azure Key Vault storage backend.

Stores the cert and key as two secrets (``<name>-cert`` / ``<name>-key``). Uses
``DefaultAzureCredential`` unless a client is injected (tests). The azure SDK is imported
lazily so it is only required when this backend is actually selected.
"""

from __future__ import annotations

import re

from fastapi.concurrency import run_in_threadpool

from .base import CertStore, StoredBundle

_SAFE = re.compile(r"[^0-9a-zA-Z-]")


def _secret_name(name: str, suffix: str) -> str:
    return f"{_SAFE.sub('-', name)}-{suffix}"


class AzureKeyVaultStore(CertStore):
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
                    "Azure Key Vault backend requires azure-identity and azure-keyvault-secrets"
                ) from exc
            self._client = SecretClient(
                vault_url=self._vault_url, credential=DefaultAzureCredential()
            )
        return self._client

    async def store(self, name: str, cert_pem: str, key_pem: str | None) -> str:
        client = self._get_client()

        def _store() -> str:
            client.set_secret(_secret_name(name, "cert"), cert_pem)
            if key_pem:
                client.set_secret(_secret_name(name, "key"), key_pem)
            return name

        return await run_in_threadpool(_store)

    async def fetch(self, reference: str) -> StoredBundle:
        client = self._get_client()

        def _fetch() -> StoredBundle:
            cert = client.get_secret(_secret_name(reference, "cert")).value
            try:
                key = client.get_secret(_secret_name(reference, "key")).value
            except Exception:  # noqa: BLE001 - key secret may not exist
                key = None
            return StoredBundle(cert_pem=cert, key_pem=key)

        return await run_in_threadpool(_fetch)

    async def delete(self, reference: str) -> None:
        client = self._get_client()

        def _delete() -> None:
            for suffix in ("cert", "key"):
                try:
                    client.begin_delete_secret(_secret_name(reference, suffix))
                except Exception:  # noqa: BLE001 - best-effort
                    pass

        await run_in_threadpool(_delete)
