"""Application configuration via environment variables (prefix ``ACME_LAN_``)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Values are read from the environment (prefix ``ACME_LAN_``) or an ``.env`` file.
    See ``.env.example`` for a documented template.
    """

    model_config = SettingsConfigDict(
        env_prefix="ACME_LAN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Downstream ACME server (what internal clients connect to) ---
    external_url: str = Field(
        default="http://localhost:8000",
        description="Public base URL of this ACME server, used to build directory URLs.",
    )
    database_url: str = Field(default="sqlite+aiosqlite:///./data/acme_lan.db")

    # http-01 downstream validation. In split-horizon LANs the identifier may resolve
    # differently than we need; this map lets us override where the validator connects
    # (identifier value -> "host[:port]"). Primarily used in tests.
    http01_timeout: float = 10.0
    http01_resolver_overrides: dict[str, str] = Field(default_factory=dict)

    # --- Upstream ACME client (the real public CA we proxy to) ---
    upstream_directory_url: str = Field(
        default="https://acme-staging-v02.api.letsencrypt.org/directory",
        description="Directory URL of the upstream CA (Let's Encrypt, ZeroSSL, Pebble...).",
    )
    upstream_account_email: str = Field(default="")
    upstream_verify_ssl: bool = Field(
        default=True,
        description="Set False for Pebble / self-signed upstreams in testing.",
    )
    upstream_account_key_path: str = Field(default="./data/upstream_account.key")
    upstream_finalize_timeout: int = Field(
        default=90, description="Seconds to wait for the upstream order to become valid."
    )

    # --- DNS provider used to satisfy the upstream DNS-01 challenge ---
    dns_provider: str = Field(default="cloudflare", description="cloudflare | challtestsrv")
    dns_propagation_seconds: int = Field(
        default=0, description="Sleep after publishing TXT before answering the challenge."
    )
    # Cloudflare
    cloudflare_api_token: str = Field(default="")
    # challtestsrv (test mock)
    challtestsrv_url: str = Field(default="http://localhost:8055")

    # --- Web dashboard / management API (single-tenant homelab) ---
    # If set, the management API and dashboard require this bearer token. Empty = open
    # (intended for trusted LANs / reverse-proxy auth). The ACME endpoints are never gated.
    admin_token: str = Field(default="")
    # Default port used when health-checking a certificate's domain.
    health_default_port: int = Field(default=443)
    health_timeout: float = Field(default=7.0)

    # --- Credential store (Phase 3) ---
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt stored device credentials.
    # Generate with: Fernet.generate_key() from cryptography.fernet.
    secret_key: str = Field(default="")

    # --- Auto-renew (Phase 3) ---
    renew_before_days: int = Field(
        default=30, description="Renew certificates with fewer than this many days remaining."
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests that mutate the environment)."""
    global _settings
    _settings = None
