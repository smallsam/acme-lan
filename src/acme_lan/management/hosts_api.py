"""Management API for managed hosts, device credentials, and deploy plugins."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..credentials import encrypt_secret
from ..db import get_session
from ..deploy.factory import available_plugins
from ..hosts import renew_and_deploy
from ..models import ManagedHost, StoredCredential
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


def _host_view(host: ManagedHost) -> dict[str, Any]:
    return {
        "id": host.id,
        "name": host.name,
        "domains": host.domains,
        "address": host.address,
        "port": host.port,
        "deploy_plugin": host.deploy_plugin,
        "credential_id": host.credential_id,
        "config": host.config,
        "enabled": host.enabled,
        "last_deployed_at": host.last_deployed_at.isoformat() if host.last_deployed_at else None,
        "last_status": host.last_status,
    }


class HostCreate(BaseModel):
    name: str
    domains: list[str]
    address: str
    port: int = 443
    deploy_plugin: str = "local"
    credential_id: str | None = None
    config: dict[str, Any] = {}
    enabled: bool = True


class HostUpdate(BaseModel):
    name: str | None = None
    domains: list[str] | None = None
    address: str | None = None
    port: int | None = None
    deploy_plugin: str | None = None
    credential_id: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


@router.get("/deploy-plugins")
async def deploy_plugins() -> list[str]:
    return available_plugins()


@router.get("/hosts")
async def list_hosts(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    hosts = (await session.execute(select(ManagedHost))).scalars().all()
    return [_host_view(h) for h in hosts]


@router.post("/hosts", status_code=201)
async def create_host(
    body: HostCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    if body.deploy_plugin not in available_plugins():
        raise HTTPException(400, f"Unknown deploy plugin {body.deploy_plugin!r}")
    host = ManagedHost(**body.model_dump())
    session.add(host)
    await session.commit()
    await session.refresh(host)
    return _host_view(host)


@router.get("/hosts/{host_id}")
async def get_host(host_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    return _host_view(host)


@router.patch("/hosts/{host_id}")
async def update_host(
    host_id: str, body: HostUpdate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    host = await session.get(ManagedHost, host_id)
    if host is None:
        raise HTTPException(404, "Host not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(host, field, value)
    session.add(host)
    await session.commit()
    await session.refresh(host)
    return _host_view(host)


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
    secret: str


def _credential_view(cred: StoredCredential) -> dict[str, Any]:
    return {
        "id": cred.id,
        "name": cred.name,
        "kind": cred.kind,
        "username": cred.username,
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
    cred = StoredCredential(
        name=body.name,
        kind=body.kind,
        username=body.username,
        secret_encrypted=encrypt_secret(body.secret),
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
