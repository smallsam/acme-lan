"""Management API for managed hosts, device credentials, and deploy plugins."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..certlifecycle import expiry_info
from ..config import get_settings
from ..credentials import encrypt_secret
from ..db import get_session
from ..deploy.factory import available_plugins, plugin_specs
from ..hosts import renew_and_deploy
from ..models import Certificate, ManagedHost, StoredCredential
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


LOCAL_KEY_WARNING = (
    "csr_source='local' means acme-lan generates and holds the private key. Prefer "
    "csr_source='device' so the key never leaves the device."
)


def _cert_summary(cert: Certificate, warn_days: int) -> dict[str, Any]:
    view = {
        "id": cert.id,
        "primary_domain": (cert.domains or [None])[0],
        "domains": cert.domains,
        "not_after": cert.not_after.isoformat() if cert.not_after else None,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "retired": cert.retired,
    }
    view.update(expiry_info(cert, warn_days))
    return view


async def _host_certs(host_id: str, session: AsyncSession) -> list[Certificate]:
    return list(
        (
            await session.execute(
                select(Certificate)
                .where(Certificate.host_id == host_id)
                .order_by(Certificate.issued_at.desc())
            )
        ).scalars().all()
    )


async def _host_view(host: ManagedHost, session: AsyncSession) -> dict[str, Any]:
    warn_days = get_settings().expiry_warn_days
    certs = await _host_certs(host.id, session)
    view = {
        "id": host.id,
        "name": host.name,
        "domains": host.domains,
        "address": host.address,
        "port": host.port,
        "deploy_plugin": host.deploy_plugin,
        "csr_source": host.csr_source,
        "credential_id": host.credential_id,
        "config": host.config,
        "enabled": host.enabled,
        "last_deployed_at": host.last_deployed_at.isoformat() if host.last_deployed_at else None,
        "last_status": host.last_status,
        # Link the host to the certificates it has been issued.
        "certificate_count": len(certs),
        "latest_certificate": _cert_summary(certs[0], warn_days) if certs else None,
    }
    if host.csr_source == "local":
        view["warning"] = LOCAL_KEY_WARNING
    return view


class HostCreate(BaseModel):
    name: str
    domains: list[str]
    address: str
    port: int = 443
    deploy_plugin: str = "local"
    csr_source: str = "device"
    credential_id: str | None = None
    config: dict[str, Any] = {}
    enabled: bool = True


class HostUpdate(BaseModel):
    name: str | None = None
    domains: list[str] | None = None
    address: str | None = None
    port: int | None = None
    deploy_plugin: str | None = None
    csr_source: str | None = None
    credential_id: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


@router.get("/deploy-plugins")
async def deploy_plugins() -> list[dict[str, Any]]:
    """Each plugin with the config fields it needs, so the UI can render a real form."""
    return plugin_specs()


@router.get("/hosts")
async def list_hosts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    hosts = (await session.execute(select(ManagedHost))).scalars().all()
    return [await _host_view(h, session) for h in hosts]


@router.post("/hosts", status_code=201)
async def create_host(
    body: HostCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    if body.deploy_plugin not in available_plugins():
        raise HTTPException(400, f"Unknown deploy plugin {body.deploy_plugin!r}")
    if body.csr_source not in ("device", "local"):
        raise HTTPException(400, "csr_source must be 'device' or 'local'")
    if body.csr_source == "device":
        from ..deploy.factory import get_deploy_plugin

        if not get_deploy_plugin(body.deploy_plugin).supports_csr_retrieval:
            raise HTTPException(
                400,
                f"deploy plugin {body.deploy_plugin!r} cannot retrieve a CSR from the device; "
                "use csr_source='local'",
            )
    host = ManagedHost(**body.model_dump())
    session.add(host)
    await session.commit()
    await session.refresh(host)
    return await _host_view(host, session)


@router.get("/hosts/{host_id}")
async def get_host(host_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    return await _host_view(host, session)


@router.get("/hosts/{host_id}/certificates")
async def host_certificates(
    host_id: str, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Certificates issued for this host (newest first) — the cert↔device link."""
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    warn_days = get_settings().expiry_warn_days
    return [_cert_summary(c, warn_days) for c in await _host_certs(host_id, session)]


@router.patch("/hosts/{host_id}")
async def update_host(
    host_id: str, body: HostUpdate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    updates = body.model_dump(exclude_unset=True)
    if "deploy_plugin" in updates and updates["deploy_plugin"] not in available_plugins():
        raise HTTPException(400, f"Unknown deploy plugin {updates['deploy_plugin']!r}")
    if updates.get("csr_source") not in (None, "device", "local"):
        raise HTTPException(400, "csr_source must be 'device' or 'local'")
    for field, value in updates.items():
        setattr(host, field, value)
    # Re-validate the device-mode requirement against the (possibly updated) plugin.
    if host.csr_source == "device":
        from ..deploy.factory import get_deploy_plugin

        if not get_deploy_plugin(host.deploy_plugin).supports_csr_retrieval:
            raise HTTPException(
                400,
                f"deploy plugin {host.deploy_plugin!r} cannot retrieve a CSR from the device",
            )
    session.add(host)
    await session.commit()
    await session.refresh(host)
    return await _host_view(host, session)


@router.delete("/hosts/{host_id}", status_code=204)
async def delete_host(host_id: str, session: AsyncSession = Depends(get_session)) -> None:
    host = await session.get(ManagedHost, host_id)
    if host is not None:
        await session.delete(host)
        await session.commit()


@router.post("/hosts/{host_id}/renew")
async def renew_host(
    host_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    cert, result = await renew_and_deploy(host, session)
    return {"ok": result.ok, "detail": result.detail, "certificate_id": cert.id}


# --- Credentials (secrets are write-only; never returned) ---
class CredentialCreate(BaseModel):
    name: str
    kind: str = "password"  # "password" | "ssh_key"
    username: str
    # local: provide `secret` (stored Fernet-encrypted). Remote (azure_keyvault | vault):
    # provide `secret_reference` (the secret is fetched from the provider at deploy time).
    provider: str = "local"
    secret: str = ""
    secret_reference: str = ""


def _credential_view(cred: StoredCredential) -> dict[str, Any]:
    return {
        "id": cred.id,
        "name": cred.name,
        "kind": cred.kind,
        "username": cred.username,
        "provider": cred.provider,
        "secret_reference": cred.secret_reference if cred.provider != "local" else None,
        "created_at": cred.created_at.isoformat() if cred.created_at else None,
    }


@router.get("/credentials")
async def list_credentials(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    creds = (await session.execute(select(StoredCredential))).scalars().all()
    return [_credential_view(c) for c in creds]


@router.post("/credentials", status_code=201)
async def create_credential(
    body: CredentialCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    if body.kind not in ("password", "ssh_key"):
        raise HTTPException(400, "kind must be 'password' or 'ssh_key'")
    if body.provider == "local":
        if not body.secret:
            raise HTTPException(400, "local credentials require 'secret'")
        cred = StoredCredential(
            name=body.name,
            kind=body.kind,
            username=body.username,
            provider="local",
            secret_encrypted=encrypt_secret(body.secret),
        )
    else:
        from ..secrets.factory import SUPPORTED

        if body.provider not in SUPPORTED:
            raise HTTPException(400, f"provider must be 'local' or one of {SUPPORTED}")
        if not body.secret_reference:
            raise HTTPException(400, f"{body.provider} credentials require 'secret_reference'")
        cred = StoredCredential(
            name=body.name,
            kind=body.kind,
            username=body.username,
            provider=body.provider,
            secret_reference=body.secret_reference,
        )
    session.add(cred)
    await session.commit()
    await session.refresh(cred)
    return _credential_view(cred)


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    cred = await session.get(StoredCredential, credential_id)
    if cred is not None:
        await session.delete(cred)
        await session.commit()
