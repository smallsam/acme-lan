"""Database models for ACME server state (RFC 8555 objects)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- ACME status vocabularies (RFC 8555 §7.1.6) ---
class OrderStatus:
    PENDING = "pending"
    READY = "ready"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"


class AuthzStatus:
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"
    DEACTIVATED = "deactivated"
    EXPIRED = "expired"
    REVOKED = "revoked"


class ChallengeStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    VALID = "valid"
    INVALID = "invalid"


class Account(SQLModel, table=True):
    __tablename__ = "account"

    id: str = Field(default_factory=_uuid, primary_key=True)
    status: str = Field(default="valid")
    key_thumbprint: str = Field(index=True)
    jwk: dict[str, Any] = Field(sa_column=Column(JSON))
    contact: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    terms_agreed: bool = False
    created_at: datetime = Field(default_factory=utcnow)


class Order(SQLModel, table=True):
    __tablename__ = "acme_order"

    id: str = Field(default_factory=_uuid, primary_key=True)
    account_id: str = Field(foreign_key="account.id", index=True)
    status: str = Field(default=OrderStatus.PENDING)
    identifiers: list[dict[str, str]] = Field(sa_column=Column(JSON))
    not_before: str | None = None
    not_after: str | None = None
    error: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    certificate_id: str | None = Field(default=None, foreign_key="certificate.id")
    expires_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class Authorization(SQLModel, table=True):
    __tablename__ = "authorization"

    id: str = Field(default_factory=_uuid, primary_key=True)
    order_id: str = Field(foreign_key="acme_order.id", index=True)
    identifier_type: str = "dns"
    identifier_value: str = ""
    wildcard: bool = False
    status: str = Field(default=AuthzStatus.PENDING)
    expires_at: datetime = Field(default_factory=utcnow)


class Challenge(SQLModel, table=True):
    __tablename__ = "challenge"

    id: str = Field(default_factory=_uuid, primary_key=True)
    authz_id: str = Field(foreign_key="authorization.id", index=True)
    type: str = "http-01"
    token: str = ""
    status: str = Field(default=ChallengeStatus.PENDING)
    validated_at: datetime | None = None
    error: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class Certificate(SQLModel, table=True):
    __tablename__ = "certificate"

    id: str = Field(default_factory=_uuid, primary_key=True)
    order_id: str | None = Field(default=None, index=True)
    # Set when acme-lan itself issued the cert for a managed host (no external ACME client).
    host_id: str | None = Field(default=None, index=True)
    pem_chain: str = ""
    serial: str | None = None
    subject: str | None = None
    domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    not_after: datetime | None = None
    issued_at: datetime = Field(default_factory=utcnow)
    # Where the private key (if acme-lan holds one) is stored: "none" (key stayed on the
    # device / external client), "local", "azure_keyvault" or "vault".
    key_storage: str = "none"
    key_reference: str | None = None  # backend-specific handle to fetch the key
    # Lifecycle: retire a cert so it stops triggering expiry warnings / auto-renewal.
    retired: bool = False
    retired_at: datetime | None = None
    retired_reason: str | None = None
    # Set when an expiry warning has been sent for this cert (a renewal is a new row, so it
    # gets warned about afresh).
    expiry_warned_at: datetime | None = None


class User(SQLModel, table=True):
    """A dashboard user: either local (password hash set) or created by an OIDC login."""

    __tablename__ = "app_user"

    id: str = Field(default_factory=_uuid, primary_key=True)
    username: str = Field(index=True)
    email: str = ""
    # PBKDF2-HMAC-SHA256, stored as "pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>".
    # Empty for users that can only sign in through OIDC.
    password_hash: str = ""
    # "local" or "oidc" — where this account came from.
    provider: str = "local"
    # OIDC subject claim, so a renamed account still maps to the same person.
    oidc_subject: str | None = Field(default=None, index=True)
    is_admin: bool = True
    disabled: bool = False
    last_login_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    """A logged-in session. Server-side so sessions can be revoked by deleting the row."""

    __tablename__ = "user_session"

    # Random opaque token; only its holder can present it (stored as-is, it is not a
    # password and is generated with 256 bits of entropy).
    token: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="app_user.id", index=True)
    expires_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class OidcState(SQLModel, table=True):
    """Short-lived CSRF/PKCE state for an in-flight OIDC authorization code exchange."""

    __tablename__ = "oidc_state"

    state: str = Field(primary_key=True)
    nonce: str = ""
    code_verifier: str = ""
    redirect_uri: str = ""
    next_url: str = ""
    expires_at: datetime = Field(default_factory=utcnow)


class HealthCheckPort(SQLModel, table=True):
    """Per-hostname TLS health-check port override.

    Issued certs don't say which port the service runs on, so the dashboard probe
    defaults to ``health_default_port``. This override is keyed by hostname (not
    certificate id) so it survives renewals, which create new certificate rows.
    """

    __tablename__ = "health_check_port"

    domain: str = Field(primary_key=True)
    port: int = 443
    updated_at: datetime = Field(default_factory=utcnow)


class StoredCredential(SQLModel, table=True):
    __tablename__ = "stored_credential"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = ""
    kind: str = "password"  # "password" | "ssh_key"
    username: str = ""
    # Where the secret lives: "local" (Fernet ciphertext in secret_encrypted), or a remote
    # provider ("azure_keyvault" | "vault") fetched by secret_reference at deploy time. The
    # same providers used for remote certificate storage are mirrored here.
    provider: str = "local"
    secret_encrypted: str = ""  # Fernet ciphertext (local provider only)
    secret_reference: str = ""  # remote provider handle (azure secret name / vault path)
    created_at: datetime = Field(default_factory=utcnow)


class ManagedHost(SQLModel, table=True):
    __tablename__ = "managed_host"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = ""
    domains: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    address: str = ""  # host / IP to deploy to and health-check
    port: int = 443
    deploy_plugin: str = "local"
    # How the CSR is obtained:
    #   "device" (preferred) — retrieve a CSR from the device; the private key never touches
    #                          acme-lan. Only the signed cert is pushed back.
    #   "local"              — acme-lan generates the key + CSR and pushes both. Less secure;
    #                          the UI warns when this is chosen.
    csr_source: str = "device"
    credential_id: str | None = Field(default=None, foreign_key="stored_credential.id")
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    last_deployed_at: datetime | None = None
    last_status: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class KeyMaterial(SQLModel, table=True):
    """Local backend storage for a cert + (Fernet-encrypted) private key bundle."""

    __tablename__ = "key_material"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = ""
    cert_pem: str = ""
    key_encrypted: str | None = None  # Fernet ciphertext, or None if no key stored
    created_at: datetime = Field(default_factory=utcnow)


class AcmeProfile(SQLModel, table=True):
    """A named ACME listener served under /acme/p/<name>/ with its own upstream CA."""

    __tablename__ = "acme_profile"

    name: str = Field(primary_key=True)
    enabled: bool = True
    # "acme" — proxy to an (optionally EAB-authenticated) upstream ACME CA (e.g. DigiCert).
    # "ca_handler" — issue from a private CA that doesn't speak ACME (acme2certifier-style).
    upstream_type: str = "acme"
    # ACME upstream settings (used when upstream_type == "acme").
    directory_url: str = ""
    verify_ssl: bool = True
    account_email: str = ""
    account_key_path: str = ""
    eab_kid: str = ""
    eab_hmac_key: str = ""
    # Private-CA handler settings (used when upstream_type == "ca_handler").
    ca_handler: str = ""
    ca_handler_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)


class Nonce(SQLModel, table=True):
    __tablename__ = "nonce"

    value: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
