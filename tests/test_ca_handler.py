"""Tests for private-CA handlers."""

from __future__ import annotations

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from acme_lan.ca.factory import available_ca_handlers, get_ca_handler
from acme_lan.ca.local_ca import LocalCaHandler, create_self_signed_ca


def _csr(domain: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode(), key


def test_local_ca_enrolls_csr():
    ca_cert_pem, ca_key_pem = create_self_signed_ca("Test WiFi CA")
    handler = LocalCaHandler({"ca_cert_pem": ca_cert_pem, "ca_key_pem": ca_key_pem})

    csr_pem, key = _csr("device.wifi.lan")
    chain = handler.enroll(csr_pem)

    certs = x509.load_pem_x509_certificates(chain.encode())
    assert len(certs) == 2  # leaf + CA
    leaf, ca = certs
    # Issued by our CA, for the CSR's key and SAN.
    assert leaf.issuer == ca.subject
    assert "Test WiFi CA" in ca.subject.rfc4514_string()
    san = leaf.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert "device.wifi.lan" in san.value.get_values_for_type(x509.DNSName)
    assert leaf.public_key().public_numbers() == key.public_key().public_numbers()

    # Signature actually verifies against the CA public key.
    ca.public_key().verify(
        leaf.signature,
        leaf.tbs_certificate_bytes,
        padding.PKCS1v15(),
        leaf.signature_hash_algorithm,
    )


def test_factory_lists_and_builds():
    assert "local_ca" in available_ca_handlers()
    assert isinstance(get_ca_handler("local_ca"), LocalCaHandler)
