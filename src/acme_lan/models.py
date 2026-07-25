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


class StoredCredential(SQLModel, table=True):
    __tablename__ = "stored_credential"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = ""
    kind: str = "password"  # "password" | "ssh_key"
    username: str = ""
    secret_encrypted: str = ""  # Fernet ciphertext of the password or private key
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


class Nonce(SQLModel, table=True):
    __tablename__ = "nonce"

    value: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
