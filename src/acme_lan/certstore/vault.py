"""HashiCorp Vault storage backend (KV v2).

Stores each bundle at ``<mount>/<prefix>/<name>`` with ``cert`` and ``key`` fields. Uses
hvac, imported lazily; a client can be injected for tests.
"""

from __future__ import annotations

from fastapi.concurrency import run_in_threadpool

from .base import CertStore, StoredBundle


class VaultCertStore(CertStore):
    name = "vault"

    def __init__(
        self, url: str, token: str, mount: str = "secret", prefix: str = "acme-lan", client=None
    ) -> None:
        self._url = url
        self._token = token
        self._mount = mount
        self._prefix = prefix.strip("/")
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                import hvac
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Vault backend requires hvac") from exc
            self._client = hvac.Client(url=self._url, token=self._token)
        return self._client

    def _path(self, name: str) -> str:
        return f"{self._prefix}/{name}" if self._prefix else name

    async def store(self, name: str, cert_pem: str, key_pem: str | None) -> str:
        client = self._get_client()
        path = self._path(name)

        def _store() -> str:
            client.secrets.kv.v2.create_or_update_secret(
                path=path,
                mount_point=self._mount,
                secret={"cert": cert_pem, "key": key_pem or ""},
            )
            return path

        return await run_in_threadpool(_store)

    async def fetch(self, reference: str) -> StoredBundle:
        client = self._get_client()

        def _fetch() -> StoredBundle:
            resp = client.secrets.kv.v2.read_secret_version(
                path=reference, mount_point=self._mount
            )
            data = resp["data"]["data"]
            return StoredBundle(cert_pem=data.get("cert", ""), key_pem=data.get("key") or None)

        return await run_in_threadpool(_fetch)

    async def delete(self, reference: str) -> None:
        client = self._get_client()

        def _delete() -> None:
            try:
                client.secrets.kv.v2.delete_metadata_and_all_versions(
                    path=reference, mount_point=self._mount
                )
            except Exception:  # noqa: BLE001 - best-effort
                pass

        await run_in_threadpool(_delete)
