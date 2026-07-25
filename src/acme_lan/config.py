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
    # How this server proves control to the upstream CA:
    #   dns-01  — publish a _acme-challenge TXT record (works for internal-only hosts).
    #   http-01 — answer from an edge HTTP server the upstream can reach (needs the edge
    #             to be publicly reachable, e.g. wildcard DNS -> edge public IP).
    upstream_challenge: str = Field(default="dns-01")
    edge_http_port: int = Field(
        default=80, description="Port the edge HTTP-01 responder listens on."
    )
    edge_public_ip: str = Field(
        default="",
        description="IP that identifiers should resolve to for edge http-01 (A-record "
        "publishing); only used by providers that support A records, e.g. challtestsrv.",
    )

    # --- DNS provider used to satisfy the upstream DNS-01 challenge ---
    dns_provider: str = Field(default="cloudflare", description="cloudflare | challtestsrv")
    dns_propagation_seconds: int = Field(
        default=0, description="Sleep after publishing TXT before answering the challenge."
    )
    # Cloudflare
    cloudflare_api_token: str = Field(default="")
    # acme-dns (delegate _acme-challenge via CNAME to an acme-dns instance)
    acmedns_api_url: str = Field(default="")
    acmedns_username: str = Field(default="")
    acmedns_password: str = Field(default="")
    acmedns_subdomain: str = Field(default="")
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

    # --- Certificate / key storage backend ---
    # local | azure_keyvault | vault. "local" keeps the (Fernet-encrypted) key in the DB.
    cert_store_backend: str = Field(default="local")
    # Azure Key Vault (uses DefaultAzureCredential unless a token is injected in tests).
    azure_keyvault_url: str = Field(default="")
    # HashiCorp Vault (KV v2).
    vault_url: str = Field(default="")
    vault_token: str = Field(default="")
    vault_mount: str = Field(default="secret")
    vault_path_prefix: str = Field(default="acme-lan")

    # --- Auto-renew scheduler ---
    renew_before_days: int = Field(
        default=30, description="Renew certificates with fewer than this many days remaining."
    )
    auto_renew_enabled: bool = Field(
        default=False, description="Run a background loop that renews due managed hosts."
    )
    renew_check_interval_seconds: int = Field(default=3600)

    # --- Self TLS certificate (serve the admin UI / ACME endpoints over trusted HTTPS) ---
    # The hostname acme-lan is reached on; when set (and self_cert_enabled), acme-lan
    # obtains and renews its own certificate via the default upstream so there are no TLS
    # warnings on the LAN.
    service_domain: str = Field(default="")
    self_cert_enabled: bool = Field(default=False)
    self_cert_path: str = Field(default="./data/service_cert.pem")
    self_cert_key_path: str = Field(default="./data/service_key.pem")
    self_cert_refresh_interval_seconds: int = Field(default=43200)  # 12h

    # --- Maintenance / GC ---
    nonce_max_age_seconds: int = Field(
        default=3600, description="Unused nonces older than this are purged."
    )

    # --- Expiry warnings / notifications ---
    expiry_warn_days: int = Field(
        default=21, description="Warn about (non-retired) certificates expiring within N days."
    )
    notify_check_interval_seconds: int = Field(default=21600)  # 6h
    # Postmark email
    postmark_server_token: str = Field(default="")
    notify_email_from: str = Field(default="")
    notify_email_to: str = Field(default="")  # comma-separated
    # Generic webhook (POST JSON)
    notify_webhook_url: str = Field(default="")


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
