"""HashiCorp Vault secret provider (device credentials).

``reference`` is ``<kv-path>`` or ``<kv-path>#<field>`` (field defaults to "value").
"""

from __future__ import annotations

from .base import SecretProvider


class VaultSecrets(SecretProvider):
    name = "vault"

    def __init__(self, url: str, token: str, mount: str = "secret", client=None) -> None:
        self._url = url
        self._token = token
        self._mount = mount
        self._client = client

    def _get_client(self):
        if self._client is None:
            try:
                import hvac
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("Vault provider requires hvac (pip install .[storage])") from exc
            self._client = hvac.Client(url=self._url, token=self._token)
        return self._client

    def get_secret(self, reference: str) -> str:
        path, _, field = reference.partition("#")
        field = field or "value"
        resp = self._get_client().secrets.kv.v2.read_secret_version(
            path=path, mount_point=self._mount
        )
        return resp["data"]["data"][field]
