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
    # Negotiated protocol, e.g. "TLSv1.2". Old appliances often top out at TLSv1/TLSv1.1,
    # which is worth showing rather than reporting as an unexplained failure.
    tls_version: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _permissive_client_context(*, verify: bool) -> ssl.SSLContext:
    """Build a client context that can still talk to legacy appliances.

    acme-lan exists to put certificates on old gear, so the probe has to be able to reach
    it: modern defaults (TLS 1.2 minimum, security level 2) refuse the TLS 1.0/1.1 and
    older ciphers that switches, iDRACs and printers offer, which would show up as a bare
    handshake failure. Certificate *verification* is unaffected — ``verify`` still decides
    that, so the trust verdict stays honest.
    """
    if verify:
        ctx = ssl.create_default_context()
    else:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    except (ValueError, OSError):  # pragma: no cover - build without TLS 1.0
        pass
    # SECLEVEL 0 for the unverified read (we only want to see the certificate); 1 when
    # verifying, so the chain still has to stand up on its own merits.
    try:
        ctx.set_ciphers("ALL:@SECLEVEL=0" if not verify else "DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:  # pragma: no cover - policy forbids lowering the level
        pass
    return ctx


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


async def _fetch_peer_cert(
    host: str, port: int, server_name: str, timeout: float
) -> tuple[bytes, str | None]:
    """Grab the peer's leaf certificate (DER) without verifying it, so we can still
    report on expired/untrusted certs. Also returns the negotiated protocol version."""
    ctx = _permissive_client_context(verify=False)
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ctx, server_hostname=server_name), timeout
    )
    try:
        ssl_obj = writer.get_extra_info("ssl_object")
        return ssl_obj.getpeercert(binary_form=True), ssl_obj.version()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


async def _is_chain_trusted(host: str, port: int, server_name: str, timeout: float) -> bool:
    """A second handshake with full verification against the system trust store."""
    ctx = _permissive_client_context(verify=True)
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
        der, tls_version = await _fetch_peer_cert(host, port, sni, timeout)
    except Exception as exc:  # noqa: BLE001
        return TlsHealth(host=host, port=port, reachable=False, error=str(exc))

    if not der:
        return TlsHealth(
            host=host, port=port, reachable=True, error="No peer certificate",
            tls_version=tls_version,
        )

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
        tls_version=tls_version,
    )
