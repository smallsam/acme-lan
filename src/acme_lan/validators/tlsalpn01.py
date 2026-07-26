"""tls-alpn-01 challenge validation (RFC 8737).

For LAN clients that would rather not run an HTTP server: the client answers by presenting
a special self-signed certificate over TLS on port 443, negotiated with the ``acme-tls/1``
ALPN protocol. acme-lan (the ACME *server*) connects, checks the negotiated protocol, and
verifies the certificate carries the ``id-pe-acmeIdentifier`` extension whose value is the
SHA-256 of the key authorization.

Split-horizon note: ``settings.tlsalpn_resolver_overrides`` maps an identifier to the
``host[:port]`` the validator should connect to (SNI is preserved), mirroring http-01.
"""

from __future__ import annotations

import asyncio
import hashlib
import ssl
from dataclasses import dataclass

from cryptography import x509

from ..config import get_settings

# id-pe-acmeIdentifier (RFC 8737 §3).
ACME_TLS_ALPN_OID = x509.ObjectIdentifier("1.3.6.1.5.5.7.1.31")
ACME_TLS_ALPN_PROTOCOL = "acme-tls/1"


@dataclass
class ValidationResult:
    ok: bool
    detail: str = ""


def _split_host_port(target: str, default_port: int) -> tuple[str, int]:
    if ":" in target:
        host, _, port = target.rpartition(":")
        return host, int(port)
    return target, default_port


async def validate_tlsalpn01(identifier: str, key_authorization: str) -> ValidationResult:
    settings = get_settings()
    override = settings.tlsalpn_resolver_overrides.get(identifier)
    host, port = _split_host_port(override or identifier, settings.tlsalpn_default_port)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols([ACME_TLS_ALPN_PROTOCOL])

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx, server_hostname=identifier),
            settings.tlsalpn_timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(False, f"Could not open acme-tls/1 connection: {exc}")

    try:
        ssl_obj = writer.get_extra_info("ssl_object")
        if ssl_obj is None or ssl_obj.selected_alpn_protocol() != ACME_TLS_ALPN_PROTOCOL:
            return ValidationResult(False, "Peer did not negotiate the acme-tls/1 protocol")
        der = ssl_obj.getpeercert(binary_form=True)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    if not der:
        return ValidationResult(False, "No certificate presented on the acme-tls/1 connection")

    cert = x509.load_der_x509_certificate(der)
    try:
        ext = cert.extensions.get_extension_for_oid(ACME_TLS_ALPN_OID)
    except x509.ExtensionNotFound:
        return ValidationResult(False, "Certificate is missing the acmeIdentifier extension")

    # The extension value is a DER OCTET STRING wrapping the 32-byte digest: 04 20 <digest>.
    expected = hashlib.sha256(key_authorization.encode("ascii")).digest()
    raw = ext.value.value if isinstance(ext.value, x509.UnrecognizedExtension) else b""
    if raw != b"\x04\x20" + expected:
        return ValidationResult(False, "acmeIdentifier does not match the key authorization")

    return ValidationResult(True)
