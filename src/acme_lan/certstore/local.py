"""Local storage backend: keep the cert + Fernet-encrypted key in the database."""

from __future__ import annotations

from ..credentials import decrypt_secret, encrypt_secret
from ..db import session_scope
from ..models import KeyMaterial
from .base import CertStore, StoredBundle


class LocalCertStore(CertStore):
    name = "local"

    async def store(self, name: str, cert_pem: str, key_pem: str | None) -> str:
        async with session_scope() as session:
            row = KeyMaterial(
                name=name,
                cert_pem=cert_pem,
                key_encrypted=encrypt_secret(key_pem) if key_pem else None,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row.id

    async def fetch(self, reference: str) -> StoredBundle:
        async with session_scope() as session:
            row = await session.get(KeyMaterial, reference)
            if row is None:
                raise KeyError(f"No stored key material for reference {reference!r}")
            key_pem = decrypt_secret(row.key_encrypted) if row.key_encrypted else None
            return StoredBundle(cert_pem=row.cert_pem, key_pem=key_pem)

    async def delete(self, reference: str) -> None:
        async with session_scope() as session:
            row = await session.get(KeyMaterial, reference)
            if row is not None:
                await session.delete(row)
                await session.commit()
