"""A self-contained private CA handler that signs CSRs with a configured CA key.

Config (any of paths or inline PEM):
  ca_cert_path / ca_cert_pem  — the CA certificate (PEM)
  ca_key_path  / ca_key_pem   — the CA private key (PEM, unencrypted)
  validity_days               — issued-cert lifetime (default 397)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.x509.oid import ExtensionOID, NameOID

from .base import CaHandler


def create_self_signed_ca(common_name: str = "acme-lan private CA") -> tuple[str, str]:
    """Generate a private CA (cert_pem, key_pem) — handy for bootstrapping / tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return cert_pem, key_pem


class LocalCaHandler(CaHandler):
    name = "local_ca"

    def _load(self) -> tuple[x509.Certificate, object]:
        cert_pem = self.config.get("ca_cert_pem")
        key_pem = self.config.get("ca_key_pem")
        if not cert_pem and self.config.get("ca_cert_path"):
            with open(self.config["ca_cert_path"]) as fh:
                cert_pem = fh.read()
        if not key_pem and self.config.get("ca_key_path"):
            with open(self.config["ca_key_path"]) as fh:
                key_pem = fh.read()
        if not cert_pem or not key_pem:
            raise ValueError("local_ca handler requires a CA cert and key (path or inline PEM)")
        ca_cert = x509.load_pem_x509_certificate(cert_pem.encode())
        ca_key = load_pem_private_key(key_pem.encode(), password=None)
        return ca_cert, ca_key

    def enroll(self, csr_pem: str) -> str:
        ca_cert, ca_key = self._load()
        csr = x509.load_pem_x509_csr(csr_pem.encode())
        if not csr.is_signature_valid:
            raise ValueError("CSR signature is not valid")

        validity_days = int(self.config.get("validity_days", 397))
        try:
            san = csr.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            ).value
        except x509.ExtensionNotFound:
            san = x509.SubjectAlternativeName([])

        builder = (
            x509.CertificateBuilder()
            .subject_name(csr.subject)
            .issuer_name(ca_cert.subject)
            .public_key(csr.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now(UTC) - timedelta(minutes=5))
            .not_valid_after(datetime.now(UTC) + timedelta(days=validity_days))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        )
        if san:
            builder = builder.add_extension(san, critical=False)
        leaf = builder.sign(ca_key, hashes.SHA256())

        leaf_pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
        ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode()
        return leaf_pem + ca_pem
