"""Tests for downstream tls-alpn-01 challenge validation (RFC 8737)."""

from __future__ import annotations

import hashlib
import socket
import ssl
import threading
from datetime import UTC, datetime, timedelta

import josepy
from acme import challenges
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from acme_lan.config import get_settings, reset_settings_cache
from acme_lan.validators.tlsalpn01 import ACME_TLS_ALPN_OID, validate_tlsalpn01

from .conftest import make_csr
from .downstream import build_downstream_client


def _build_validation_cert(identifier: str, key_authorization: str, tmp_path) -> tuple[str, str]:
    """Build the RFC 8737 validation cert (with the acmeIdentifier extension) + key files."""
    key = ec.generate_private_key(ec.SECP256R1())
    digest = hashlib.sha256(key_authorization.encode()).digest()
    ext_value = b"\x04\x20" + digest  # DER OCTET STRING of the 32-byte digest
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, identifier)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(identifier)]), critical=False)
        .add_extension(x509.UnrecognizedExtension(ACME_TLS_ALPN_OID, ext_value), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_file = tmp_path / "alpn-cert.pem"
    key_file = tmp_path / "alpn-key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(cert_file), str(key_file)


class AlpnServer:
    """A minimal threaded TLS server presenting a cert over the acme-tls/1 ALPN protocol."""

    def __init__(self, cert_file: str, key_file: str, *, alpn: bool = True) -> None:
        self._ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ctx.load_cert_chain(cert_file, key_file)
        if alpn:
            self._ctx.set_alpn_protocols(["acme-tls/1"])
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self._sock.settimeout(0.5)
        self.port = self._sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self) -> None:
        while not self._stop:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                continue
            try:
                tls = self._ctx.wrap_socket(conn, server_side=True)
                tls.close()
            except Exception:  # noqa: BLE001 - handshake probes can fail; keep serving
                try:
                    conn.close()
                except OSError:
                    pass

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop = True
        try:
            self._sock.close()
        except OSError:
            pass


def _override(identifier: str, port: int) -> None:
    reset_settings_cache()
    get_settings().tlsalpn_resolver_overrides[identifier] = f"127.0.0.1:{port}"


async def test_validate_tlsalpn01_success(tmp_path):
    domain, keyauth = "db.lan.test", "tok123.thumbprintvalue"
    server = AlpnServer(*_build_validation_cert(domain, keyauth, tmp_path))
    server.start()
    _override(domain, server.port)
    try:
        assert (await validate_tlsalpn01(domain, keyauth)).ok is True
        # Wrong key authorization -> the acmeIdentifier digest won't match.
        assert (await validate_tlsalpn01(domain, "wrong")).ok is False
    finally:
        server.stop()


async def test_validate_tlsalpn01_requires_alpn(tmp_path):
    domain, keyauth = "db.lan.test", "tok.thumb"
    server = AlpnServer(*_build_validation_cert(domain, keyauth, tmp_path), alpn=False)
    server.start()
    _override(domain, server.port)
    try:
        result = await validate_tlsalpn01(domain, keyauth)
        assert result.ok is False
        assert "acme-tls/1" in result.detail
    finally:
        server.stop()


def test_tlsalpn01_full_flow(make_server, tmp_path):
    """A standard ACME client validates via tls-alpn-01 end-to-end against acme-lan."""
    base = make_server()
    acme_client, account_key = build_downstream_client(base)
    domain = "db.lan.test"
    csr_pem, _key = make_csr([domain])

    orderr = acme_client.new_order(csr_pem)
    authz = orderr.authorizations[0]
    # tls-alpn-01 has no client class in the acme library, so it arrives as an
    # UnrecognizedChallenge — match on the raw JSON "type".
    challb = next(
        c for c in authz.body.challenges
        if c.chall.to_partial_json().get("type") == "tls-alpn-01"
    )

    token = challb.chall.to_partial_json()["token"]
    thumbprint = josepy.b64.b64encode(account_key.thumbprint()).decode()
    key_authorization = f"{token}.{thumbprint}"

    server = AlpnServer(*_build_validation_cert(domain, key_authorization, tmp_path))
    server.start()
    # Point the acme-lan server's validator at our local ALPN responder.
    get_settings().tlsalpn_resolver_overrides[domain] = f"127.0.0.1:{server.port}"
    try:
        acme_client.answer_challenge(challb, challenges.ChallengeResponse())
        updated, _resp = acme_client.poll(authz)
        assert updated.body.status.name == "valid" or str(updated.body.status) == "valid"
    finally:
        server.stop()
