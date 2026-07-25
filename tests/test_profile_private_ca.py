"""End-to-end: a named ACME listener backed by a private CA (no external upstream).

Demonstrates the multi-listener + acme2certifier-style private-CA path: a standard ACME
client points at /acme/p/<profile>/directory and receives a certificate signed by an
internal CA — the WiFi/private-CA use case — all from one acme-lan server.
"""

from __future__ import annotations

import httpx
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

from acme_lan.ca.local_ca import create_self_signed_ca

from .conftest import make_csr
from .downstream import answer_http01_challenges, build_downstream_client


def test_private_ca_profile_issues_via_standard_acme_client(make_server, challenge_responder):
    base = make_server()
    ca_cert_pem, ca_key_pem = create_self_signed_ca("Test WiFi CA")

    # Configure a listener profile whose upstream is a private CA (ca_handler).
    resp = httpx.post(
        f"{base}/api/acme-profiles",
        json={
            "name": "wifi",
            "upstream_type": "ca_handler",
            "ca_handler": "local_ca",
            "ca_handler_config": {"ca_cert_pem": ca_cert_pem, "ca_key_pem": ca_key_pem},
        },
        timeout=10,
    )
    assert resp.status_code == 201, resp.text

    # A standard ACME client targets the profile's directory.
    acme_client, account_key = build_downstream_client(
        base, directory_url=f"{base}/acme/p/wifi/directory"
    )
    domain = "device.wifi.lan"
    csr_pem, client_key = make_csr([domain])
    csr = x509.load_pem_x509_csr(csr_pem)

    orderr = acme_client.new_order(csr_pem)
    answer_http01_challenges(acme_client, account_key, orderr, challenge_responder)
    finalized = acme_client.poll_and_finalize(orderr)

    chain = x509.load_pem_x509_certificates(finalized.fullchain_pem.encode())
    leaf, ca = chain
    # Signed by our private CA, for the client's key + domain.
    assert "Test WiFi CA" in ca.subject.rfc4514_string()
    assert leaf.issuer == ca.subject
    san = leaf.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
    assert domain in san.value.get_values_for_type(x509.DNSName)
    assert leaf.public_key().public_numbers() == csr.public_key().public_numbers()
