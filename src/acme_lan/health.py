"""Realtime TLS certificate health probing.

Opens a raw TLS connection to an arbitrary ``host:port`` and inspects the leaf
certificate. It deliberately does **not** assume HTTPS — it only does a TLS handshake —
so it works for LDAPS, SMTPS, FTPS, and any other TLS-wrapped protocol. This is the
``check_ssl_cert``-style probe the dashboard runs live when viewed.
"""

from __future__ import annotations

import asyncio
import ssl
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID


@dataclass
class TlsHealth:
    host: str
    port: int
    reachable: bool
    error: str | None = None
    subject: str | None = None
    issuer: str | None = None
    serial: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    days_remaining: int | None = None
    expired: bool | None = None
    self_signed: bool | None = None
    chain_trusted: bool | None = None
    san: list[str] | None = None
    name_matches: bool | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _san_names(cert: x509.Certificate) -> list[str]:
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        return list(ext.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        return []


def _name_matches(names: list[str], server_name: str) -> bool:
    for pattern in names:
        if pattern == server_name:
            return True
        if pattern.startswith("*.") and server_name.split(".", 1)[-1] == pattern[2:]:
            return True
    return False


async def _fetch_peer_cert(host: str, port: int, server_name: str, timeout: float) -> bytes:
    """Grab the peer's leaf certificate (DER) without verifying it, so we can still
    report on expired/untrusted certs."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ctx, server_hostname=server_name), timeout
    )
    try:
        ssl_obj = writer.get_extra_info("ssl_object")
        return ssl_obj.getpeercert(binary_form=True)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def _is_chain_trusted(host: str, port: int, server_name: str, timeout: float) -> bool:
    """A second handshake with full verification against the system trust store."""
    ctx = ssl.create_default_context()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, server_hostname=server_name), timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except ssl.SSLCertVerificationError:
        return False
    except Exception:  # noqa: BLE001 - unreachable / other TLS errors -> treat as untrusted
        return False


async def probe_tls(
    host: str, port: int = 443, server_name: str | None = None, timeout: float = 7.0
) -> TlsHealth:
    """Probe ``host:port`` and return a :class:`TlsHealth` snapshot."""
    sni = server_name or host
    try:
        der = await _fetch_peer_cert(host, port, sni, timeout)
    except Exception as exc:  # noqa: BLE001
        return TlsHealth(host=host, port=port, reachable=False, error=str(exc))

    if not der:
        return TlsHealth(host=host, port=port, reachable=True, error="No peer certificate")

    cert = x509.load_der_x509_certificate(der)
    now = datetime.now(UTC)
    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    san = _san_names(cert)
    trusted = await _is_chain_trusted(host, port, sni, timeout)

    def _cn(name: x509.Name) -> str:
        attrs = name.get_attributes_for_oid(NameOID.COMMON_NAME)
        return attrs[0].value if attrs else name.rfc4514_string()

    return TlsHealth(
        host=host,
        port=port,
        reachable=True,
        subject=cert.subject.rfc4514_string(),
        issuer=cert.issuer.rfc4514_string(),
        serial=format(cert.serial_number, "x"),
        not_before=not_before.isoformat(),
        not_after=not_after.isoformat(),
        days_remaining=(not_after - now).days,
        expired=now > not_after,
        self_signed=cert.subject == cert.issuer,
        chain_trusted=trusted,
        san=san,
        name_matches=_name_matches(san or [_cn(cert.subject)], sni),
    )
