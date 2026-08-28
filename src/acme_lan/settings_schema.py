"""Presentation metadata for the settings screen.

:mod:`acme_lan.config` owns the settings themselves; this module says how to *show* them:
which section and sub-section a field belongs to, its human label, whether it is only
relevant given some other choice, and — importantly — whether its value is a secret that
must never be sent back to the browser.

``SECRET_FIELDS`` is deliberately an explicit list rather than a name pattern: a heuristic
that guesses from the name would silently start leaking the day someone adds a field it
doesn't recognise. ``test_settings_api`` asserts that every credential-ish field name is
either listed here or explicitly acknowledged as safe, so a new secret can't slip through.
"""

from __future__ import annotations

from dataclasses import dataclass

# Ordered sections of the settings screen.
GROUPS: list[tuple[str, str, str]] = [
    ("server", "Server", "How this ACME server presents itself to internal clients."),
    ("auth", "Authentication", "Who may use the dashboard and management API."),
    ("upstream", "Upstream CA", "The public CA acme-lan proxies to, and how it proves control."),
    ("dns", "DNS provider", "Used to answer the upstream DNS-01 challenge."),
    ("storage", "Certificate & key storage", "Where issued keys and certificates are kept."),
    ("renewal", "Renewal & health", "Automatic renewal, expiry warnings and TLS probing."),
    ("selftls", "Self TLS", "Serving acme-lan's own dashboard over a trusted certificate."),
    ("notifications", "Notifications", "Where expiry warnings are sent."),
    ("advanced", "Advanced", "Timeouts, validation overrides and maintenance."),
]

# Values that must be masked in API responses.
SECRET_FIELDS: frozenset[str] = frozenset(
    {
        "secret_key",
        "admin_token",
        "cloudflare_api_token",
        "acmedns_password",
        "vault_token",
        "postmark_server_token",
        "oidc_client_secret",
    }
)

# Fields whose names look credential-ish but hold no secret (paths, URLs, identifiers).
# Listed so the guard test can tell "safe by inspection" from "forgotten".
NON_SECRET_CREDENTIAL_LIKE: frozenset[str] = frozenset(
    {
        "upstream_account_key_path",
        "self_cert_key_path",
        "self_cert_path",
        "acmedns_username",
        "acmedns_subdomain",
        "acmedns_api_url",
        "azure_keyvault_url",
        "vault_url",
        "vault_mount",
        "vault_path_prefix",
        "oidc_client_id",
        "oidc_tenant_id",
        "oidc_discovery_url",
        "oidc_scopes",
        "oidc_allowed_emails",
        "eab_kid",
    }
)

# Fields with a fixed set of valid values, so the UI can render a select.
CHOICES: dict[str, list[str]] = {
    "dns_provider": ["cloudflare", "acmedns", "challtestsrv"],
    "cert_store_backend": ["local", "azure_keyvault", "vault"],
    "upstream_challenge": ["dns-01", "http-01"],
    "oidc_provider": ["generic", "entra"],
}


@dataclass(frozen=True)
class Meta:
    """How one setting is presented."""

    group: str
    label: str
    # Sub-section heading within the group; "" keeps the field at the top of the group.
    subgroup: str = ""
    # (other field, values that make this one apply). When the other field holds a
    # different value, the UI shows this one as not in use instead of hiding it — hiding
    # would make settings appear to vanish.
    depends_on: tuple[str, tuple[str, ...]] | None = None
    # Extra guidance where the label alone isn't enough. Falls back to the pydantic
    # description; only written here when that is missing or worth sharpening.
    help: str = ""


# Declaration order is preserved within each subgroup, so the most important option in a
# section can be listed first.
FIELD_META: dict[str, Meta] = {
    # --- Server ---
    "external_url": Meta(
        "server", "External URL",
        help="The base URL clients use to reach acme-lan. Directory URLs, the OIDC "
             "redirect URI and the self-TLS domain are all derived from it.",
    ),
    "tls_port": Meta("server", "HTTPS port"),
    "database_url": Meta(
        "server", "Database URL",
        help="SQLAlchemy URL for the state database. Changing it starts from an empty "
             "database; move the file instead if you want to keep history.",
    ),
    # --- Authentication ---
    "auth_required": Meta(
        "auth", "Require login",
        help="Off means anyone who can reach the dashboard may use it — appropriate only "
             "behind a trusted network or an authenticating proxy.",
    ),
    "session_lifetime_hours": Meta(
        "auth", "Session lifetime (hours)", help="How long a sign-in lasts before it expires."
    ),
    "admin_token": Meta(
        "auth", "Admin API token",
        help="Bearer token for scripts and automation. Leave empty to disable token access.",
    ),
    "oidc_enabled": Meta("auth", "Enable OIDC login", subgroup="Single sign-on"),
    "oidc_provider": Meta(
        "auth", "OIDC provider", subgroup="Single sign-on",
        help="Choose entra to derive every endpoint from a tenant ID, or generic to supply "
             "a discovery URL.",
    ),
    "oidc_tenant_id": Meta(
        "auth", "Entra directory (tenant) ID", subgroup="Single sign-on",
        depends_on=("oidc_provider", ("entra",)),
        help="Found on the app registration's Overview page.",
    ),
    "oidc_discovery_url": Meta(
        "auth", "OIDC discovery URL", subgroup="Single sign-on",
        depends_on=("oidc_provider", ("generic",)),
        help="The provider's .well-known/openid-configuration endpoint.",
    ),
    "oidc_client_id": Meta("auth", "OIDC client ID", subgroup="Single sign-on"),
    "oidc_client_secret": Meta("auth", "OIDC client secret", subgroup="Single sign-on"),
    "oidc_scopes": Meta(
        "auth", "OIDC scopes", subgroup="Single sign-on",
        help="Space-separated. openid is required; email and profile populate the account.",
    ),
    "oidc_auto_create_users": Meta("auth", "Create users on first OIDC login",
                                   subgroup="Single sign-on"),
    "oidc_allowed_emails": Meta("auth", "Allowed email addresses", subgroup="Single sign-on"),
    # --- Upstream CA: challenge type first, then the settings each choice uses ---
    "upstream_challenge": Meta(
        "upstream", "Challenge type",
        help="How acme-lan proves control to the upstream CA. dns-01 works for hosts that "
             "aren't reachable from the internet and uses the DNS provider settings; "
             "http-01 is faster but the edge responder must be publicly reachable.",
    ),
    "edge_http_port": Meta(
        "upstream", "Edge responder port", subgroup="HTTP-01 (edge)",
        depends_on=("upstream_challenge", ("http-01",)),
        help="Port the edge HTTP-01 responder listens on; the CA must reach it on port 80.",
    ),
    "edge_public_ip": Meta(
        "upstream", "Edge public IP", subgroup="HTTP-01 (edge)",
        depends_on=("upstream_challenge", ("http-01",)),
    ),
    "upstream_directory_url": Meta(
        "upstream", "Directory URL", subgroup="CA account",
        help="ACME directory of the CA to proxy to. Use the staging URL while testing — "
             "production has strict rate limits.",
    ),
    "upstream_account_email": Meta(
        "upstream", "Account email", subgroup="CA account",
        help="Contact address registered with the CA; used for expiry notices from them.",
    ),
    "upstream_account_key_path": Meta(
        "upstream", "Account key name", subgroup="CA account",
        help="Storage name for the upstream account key. The key is kept encrypted, not at "
             "this path.",
    ),
    "upstream_verify_ssl": Meta(
        "upstream", "Verify upstream TLS", subgroup="CA account",
        help="Turn off only for a test CA such as Pebble with a self-signed certificate.",
    ),
    "upstream_finalize_timeout": Meta(
        "upstream", "Finalize timeout (s)", subgroup="CA account",
        help="How long to wait for the CA to issue after the challenge is answered.",
    ),
    # --- DNS provider: the choice first, then each provider's own settings ---
    "dns_provider": Meta(
        "dns", "Provider",
        help="Which DNS API publishes the _acme-challenge TXT record. Only the matching "
             "section below is used.",
    ),
    "dns_propagation_seconds": Meta(
        "dns", "Propagation wait (s)",
        help="Pause after publishing the record so the CA doesn't check before it is "
             "visible. Raise it if validation fails intermittently.",
    ),
    "cloudflare_api_token": Meta(
        "dns", "API token", subgroup="Cloudflare",
        depends_on=("dns_provider", ("cloudflare",)),
        help="Token with Zone.DNS:Edit on the zones you issue for.",
    ),
    "acmedns_api_url": Meta("dns", "API URL", subgroup="acme-dns",
                            depends_on=("dns_provider", ("acmedns",))),
    "acmedns_username": Meta("dns", "Username", subgroup="acme-dns",
                             depends_on=("dns_provider", ("acmedns",))),
    "acmedns_password": Meta("dns", "Password", subgroup="acme-dns",
                             depends_on=("dns_provider", ("acmedns",))),
    "acmedns_subdomain": Meta(
        "dns", "Subdomain", subgroup="acme-dns",
        depends_on=("dns_provider", ("acmedns",)),
        help="The subdomain acme-dns allocated when you registered; your zone CNAMEs to it.",
    ),
    "challtestsrv_url": Meta(
        "dns", "Management URL", subgroup="challtestsrv (testing)",
        depends_on=("dns_provider", ("challtestsrv",)),
        help="Mock DNS server used by the end-to-end tests. Not for production.",
    ),
    # --- Storage ---
    "cert_store_backend": Meta(
        "storage", "Backend",
        help="Where issued private keys and certificates are stored. Only the matching "
             "section below is used.",
    ),
    "secret_key": Meta(
        "storage", "Encryption key (Fernet)",
        help="Encrypts stored keys and device credentials. Required for device push and "
             "self-TLS. Replacing it makes existing encrypted data unreadable.",
    ),
    "azure_keyvault_url": Meta("storage", "Vault URL", subgroup="Azure Key Vault",
                               depends_on=("cert_store_backend", ("azure_keyvault",))),
    "vault_url": Meta("storage", "Address", subgroup="HashiCorp Vault",
                      depends_on=("cert_store_backend", ("vault",))),
    "vault_token": Meta("storage", "Token", subgroup="HashiCorp Vault",
                        depends_on=("cert_store_backend", ("vault",))),
    "vault_mount": Meta(
        "storage", "KV mount", subgroup="HashiCorp Vault",
        depends_on=("cert_store_backend", ("vault",)),
        help="Name of the KV v2 secrets engine mount.",
    ),
    "vault_path_prefix": Meta(
        "storage", "Path prefix", subgroup="HashiCorp Vault",
        depends_on=("cert_store_backend", ("vault",)),
        help="Secrets are written under this path inside the mount.",
    ),
    # --- Renewal & health ---
    "auto_renew_enabled": Meta(
        "renewal", "Auto-renew managed hosts",
        help="Run a background loop that reissues and redeploys device certificates before "
             "they expire.",
    ),
    "renew_before_days": Meta(
        "renewal", "Renew before (days)",
        help="Renew once a certificate has fewer than this many days left. Also the point "
             "at which an ACME client is judged overdue.",
    ),
    "renew_check_interval_seconds": Meta("renewal", "Renewal check interval (s)"),
    "expiry_warn_days": Meta(
        "renewal", "Warn before expiry (days)",
        help="Send an expiry notification this far ahead.",
    ),
    "notify_check_interval_seconds": Meta("renewal", "Warning check interval (s)"),
    "health_default_port": Meta(
        "renewal", "Default health port", subgroup="TLS health probe",
        help="Port probed when a certificate has no per-host port set.",
    ),
    "health_timeout": Meta("renewal", "Probe timeout (s)", subgroup="TLS health probe"),
    "health_resolver_overrides": Meta(
        "renewal", "Address overrides", subgroup="TLS health probe",
        help='JSON of name to "host[:port]", for split-horizon names that resolve '
             "differently from where they should be probed.",
    ),
    # --- Self TLS ---
    "self_cert_enabled": Meta(
        "selftls", "Serve own HTTPS",
        help="Obtain a certificate for this server and serve the dashboard over it. Needs "
             "an encryption key.",
    ),
    "service_domain": Meta(
        "selftls", "Service domain",
        help="Name to certify. Defaults to the hostname of the external URL.",
    ),
    "self_cert_path": Meta("selftls", "Certificate path"),
    "self_cert_key_path": Meta(
        "selftls", "Key path (storage name)",
        help="Storage name for the service key; it is held encrypted, never written here "
             "in the clear.",
    ),
    "self_cert_refresh_interval_seconds": Meta("selftls", "Refresh interval (s)"),
    # --- Notifications ---
    "notify_email_to": Meta(
        "notifications", "To addresses", help="Comma-separated recipients for expiry warnings."
    ),
    "notify_email_from": Meta(
        "notifications", "From address", help="Must be a verified sender in Postmark."
    ),
    "postmark_server_token": Meta(
        "notifications", "Postmark server token", help="Enables email notifications when set."
    ),
    "notify_webhook_url": Meta(
        "notifications", "Webhook URL", help="Receives a JSON POST for each warning."
    ),
    # --- Advanced ---
    "http01_timeout": Meta("advanced", "http-01 timeout (s)", subgroup="Downstream validation"),
    "http01_resolver_overrides": Meta(
        "advanced", "http-01 address overrides", subgroup="Downstream validation",
        help='JSON of identifier to "host[:port]" for split-horizon LANs.',
    ),
    "tlsalpn_timeout": Meta("advanced", "tls-alpn-01 timeout (s)",
                            subgroup="Downstream validation"),
    "tlsalpn_default_port": Meta("advanced", "tls-alpn-01 port", subgroup="Downstream validation"),
    "tlsalpn_resolver_overrides": Meta(
        "advanced", "tls-alpn-01 address overrides", subgroup="Downstream validation",
        help='JSON of identifier to "host[:port]" for split-horizon LANs.',
    ),
    "nonce_max_age_seconds": Meta(
        "advanced", "Nonce max age (s)", subgroup="Maintenance",
        help="Unused ACME nonces older than this are purged.",
    ),
}

def meta_for(name: str) -> Meta:
    existing = FIELD_META.get(name)
    if existing is not None:
        return existing
    return Meta("advanced", name.replace("_", " ").capitalize())


def field_group(name: str) -> str:
    return meta_for(name).group


def field_label(name: str) -> str:
    return meta_for(name).label or name.replace("_", " ").capitalize()


def is_secret(name: str) -> bool:
    return name in SECRET_FIELDS


def subgroup_order(group_id: str) -> list[str]:
    """Sub-section titles for a group, in declaration order ("" first)."""
    seen: list[str] = []
    for name, meta in FIELD_META.items():  # noqa: B007 - name unused, order matters
        if meta.group != group_id:
            continue
        if meta.subgroup not in seen:
            seen.append(meta.subgroup)
    return seen
