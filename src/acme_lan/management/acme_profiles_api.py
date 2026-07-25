"""Management API for ACME listener profiles (extra upstreams / private CAs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..ca.factory import available_ca_handlers
from ..db import get_session
from ..models import AcmeProfile
from .auth import require_admin

router = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])


def _view(p: AcmeProfile) -> dict[str, Any]:
    return {
        "name": p.name,
        "enabled": p.enabled,
        "upstream_type": p.upstream_type,
        "directory_url": p.directory_url,
        "verify_ssl": p.verify_ssl,
        "account_email": p.account_email,
        "eab_kid": p.eab_kid,
        "eab_configured": bool(p.eab_kid and p.eab_hmac_key),  # never expose the HMAC key
        "ca_handler": p.ca_handler,
        "ca_handler_config": p.ca_handler_config,
        "directory_url_public": f"/acme/p/{p.name}/directory",
    }


class ProfileCreate(BaseModel):
    name: str
    upstream_type: str = "acme"
    enabled: bool = True
    directory_url: str = ""
    verify_ssl: bool = True
    account_email: str = ""
    account_key_path: str = ""
    eab_kid: str = ""
    eab_hmac_key: str = ""
    ca_handler: str = ""
    ca_handler_config: dict[str, Any] = {}


class ProfileUpdate(BaseModel):
    enabled: bool | None = None
    directory_url: str | None = None
    verify_ssl: bool | None = None
    account_email: str | None = None
    eab_kid: str | None = None
    eab_hmac_key: str | None = None
    ca_handler: str | None = None
    ca_handler_config: dict[str, Any] | None = None


def _validate(upstream_type: str, ca_handler: str, directory_url: str) -> None:
    if upstream_type not in ("acme", "ca_handler"):
        raise HTTPException(400, "upstream_type must be 'acme' or 'ca_handler'")
    if upstream_type == "acme" and not directory_url:
        raise HTTPException(400, "acme profiles require a directory_url")
    if upstream_type == "ca_handler":
        if not ca_handler:
            raise HTTPException(400, "ca_handler profiles require a ca_handler name")
        if ca_handler not in available_ca_handlers():
            raise HTTPException(400, f"Unknown ca_handler {ca_handler!r}")


@router.get("/ca-handlers")
async def ca_handlers() -> list[str]:
    return available_ca_handlers()


@router.get("/acme-profiles")
async def list_profiles(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(AcmeProfile))).scalars().all()
    return [_view(p) for p in rows]


@router.post("/acme-profiles", status_code=201)
async def create_profile(
    body: ProfileCreate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    if body.name in ("default", "p") or "/" in body.name:
        raise HTTPException(400, "invalid profile name")
    if await session.get(AcmeProfile, body.name) is not None:
        raise HTTPException(409, "profile already exists")
    _validate(body.upstream_type, body.ca_handler, body.directory_url)
    profile = AcmeProfile(**body.model_dump())
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _view(profile)


@router.get("/acme-profiles/{name}")
async def get_profile(name: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    profile = await session.get(AcmeProfile, name)
    if profile is None:
        raise HTTPException(404, "profile not found")
    return _view(profile)


@router.patch("/acme-profiles/{name}")
async def update_profile(
    name: str, body: ProfileUpdate, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    profile = await session.get(AcmeProfile, name)
    if profile is None:
        raise HTTPException(404, "profile not found")
    for field_name, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field_name, value)
    _validate(profile.upstream_type, profile.ca_handler, profile.directory_url)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return _view(profile)


@router.delete("/acme-profiles/{name}", status_code=204)
async def delete_profile(name: str, session: AsyncSession = Depends(get_session)) -> None:
    profile = await session.get(AcmeProfile, name)
    if profile is not None:
        await session.delete(profile)
        await session.commit()
