"""Select a DNS provider implementation from configuration."""

from __future__ import annotations

from ..config import Settings, get_settings
from .base import DnsProvider
from .challtestsrv import ChallTestSrvProvider
from .cloudflare import CloudflareProvider


def get_dns_provider(settings: Settings | None = None) -> DnsProvider:
    settings = settings or get_settings()
    provider = settings.dns_provider.lower()
    if provider == "cloudflare":
        return CloudflareProvider(settings.cloudflare_api_token)
    if provider == "challtestsrv":
        return ChallTestSrvProvider(settings.challtestsrv_url)
    raise ValueError(f"Unknown DNS provider {settings.dns_provider!r}")
