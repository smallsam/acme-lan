"""Resolve a listener profile to its upstream CA configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import AcmeProfile
from .encoding import DEFAULT_PROFILE
from .errors import AcmeError


@dataclass
class ProfileUpstream:
    """Everything fulfilment needs to issue a cert for a given listener profile."""

    profile: str
    upstream_type: str  # "acme" | "ca_handler"
    directory_url: str = ""
    verify_ssl: bool = True
    account_email: str = ""
    account_key_path: str = ""
    eab_kid: str = ""
    eab_hmac_key: str = ""
    ca_handler: str = ""
    ca_handler_config: dict[str, Any] = field(default_factory=dict)


async def resolve_profile_upstream(profile: str, session: AsyncSession) -> ProfileUpstream:
    """Return the upstream config for ``profile`` (the default profile uses global settings)."""
    if profile == DEFAULT_PROFILE:
        s = get_settings()
        return ProfileUpstream(
            profile=DEFAULT_PROFILE,
            upstream_type="acme",
            directory_url=s.upstream_directory_url,
            verify_ssl=s.upstream_verify_ssl,
            account_email=s.upstream_account_email,
            account_key_path=s.upstream_account_key_path,
        )

    row = await session.get(AcmeProfile, profile)
    if row is None or not row.enabled:
        raise AcmeError("malformed", f"Unknown or disabled ACME profile {profile!r}", status=404)
    return ProfileUpstream(
        profile=row.name,
        upstream_type=row.upstream_type,
        directory_url=row.directory_url,
        verify_ssl=row.verify_ssl,
        account_email=row.account_email,
        account_key_path=row.account_key_path or f"./data/upstream_{row.name}.key",
        eab_kid=row.eab_kid,
        eab_hmac_key=row.eab_hmac_key,
        ca_handler=row.ca_handler,
        ca_handler_config=dict(row.ca_handler_config or {}),
    )
