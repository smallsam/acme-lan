"""Authorization checks on ACME account and revocation endpoints.

These cover cross-account access control: without them a client holding any valid
account key could act on resources belonging to other accounts.
"""

from __future__ import annotations

import json
import os

import josepy
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from starlette.testclient import TestClient

from acme_lan.acme.encoding import b64url_encode

BASE = "http://localhost:8000"


@pytest.fixture
def client(tmp_path):
    os.environ["ACME_LAN_EXTERNAL_URL"] = BASE
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/authz.sqlite"
    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None
    from acme_lan.main import create_app

    with TestClient(create_app()) as c:
        yield c


def _new_key() -> josepy.JWKRSA:
    return josepy.JWKRSA(
        key=josepy.ComparableRSAKey(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    )


def _sign(key: josepy.JWKRSA, protected: dict, payload: dict | None) -> str:
    protected_b64 = b64url_encode(json.dumps(protected).encode())
    payload_b64 = "" if payload is None else b64url_encode(json.dumps(payload).encode())
    signing_input = f"{protected_b64}.{payload_b64}".encode("ascii")
    sig = key.key._wrapped.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return json.dumps(
        {"protected": protected_b64, "payload": payload_b64, "signature": b64url_encode(sig)}
    )


def _post(client, path: str, body: str):
    return client.post(path, content=body, headers={"Content-Type": "application/jose+json"})


def _nonce(client) -> str:
    return client.get("/acme/new-nonce").headers["Replay-Nonce"]


def _register(client, key: josepy.JWKRSA, email: str) -> str:
    """Register an account and return its id."""
    body = _sign(
        key,
        {
            "alg": "RS256",
            "jwk": key.public_key().to_json(),
            "nonce": _nonce(client),
            "url": f"{BASE}/acme/new-account",
        },
        {"termsOfServiceAgreed": True, "contact": [f"mailto:{email}"]},
    )
    resp = _post(client, "/acme/new-account", body)
    assert resp.status_code in (200, 201), resp.text
    return resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]


def _acct_request(client, signer: josepy.JWKRSA, signer_id: str, target_id: str, payload):
    body = _sign(
        signer,
        {
            "alg": "RS256",
            "kid": f"{BASE}/acme/acct/{signer_id}",
            "nonce": _nonce(client),
            "url": f"{BASE}/acme/acct/{target_id}",
        },
        payload,
    )
    return _post(client, f"/acme/acct/{target_id}", body)


# --- account resource ---


def test_account_can_read_and_update_itself(client):
    key = _new_key()
    acct_id = _register(client, key, "owner@example.com")

    resp = _acct_request(client, key, acct_id, acct_id, None)  # POST-as-GET
    assert resp.status_code == 200
    assert resp.json()["contact"] == ["mailto:owner@example.com"]

    resp = _acct_request(
        client, key, acct_id, acct_id, {"contact": ["mailto:new@example.com"]}
    )
    assert resp.status_code == 200
    assert resp.json()["contact"] == ["mailto:new@example.com"]


def test_other_account_cannot_read_account(client):
    victim_id = _register(client, _new_key(), "victim@example.com")
    attacker = _new_key()
    attacker_id = _register(client, attacker, "attacker@example.com")

    resp = _acct_request(client, attacker, attacker_id, victim_id, None)
    assert resp.status_code == 401, resp.text


def test_other_account_cannot_modify_or_deactivate_account(client):
    victim_key = _new_key()
    victim_id = _register(client, victim_key, "victim@example.com")
    attacker = _new_key()
    attacker_id = _register(client, attacker, "attacker@example.com")

    resp = _acct_request(
        client,
        attacker,
        attacker_id,
        victim_id,
        {"contact": ["mailto:pwned@evil.example"], "status": "deactivated"},
    )
    assert resp.status_code == 401, resp.text

    # The victim's record is untouched and still usable.
    resp = _acct_request(client, victim_key, victim_id, victim_id, None)
    assert resp.status_code == 200
    assert resp.json()["contact"] == ["mailto:victim@example.com"]
    assert resp.json()["status"] == "valid"


def test_deactivated_account_cannot_make_further_requests(client):
    key = _new_key()
    acct_id = _register(client, key, "leaving@example.com")

    resp = _acct_request(client, key, acct_id, acct_id, {"status": "deactivated"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "deactivated"

    resp = _acct_request(client, key, acct_id, acct_id, None)
    assert resp.status_code == 401, resp.text


# --- revocation ---


def _self_signed(cn: str):
    """Return (cert, key) for a stand-in 'issued' certificate."""
    from datetime import UTC, datetime, timedelta

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(days=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _store_issued_cert(account_id: str, cert):
    """Persist an Order + Certificate for ``account_id`` covering ``cert``."""
    import asyncio

    from cryptography.hazmat.primitives.serialization import Encoding

    from acme_lan.db import session_scope
    from acme_lan.models import Certificate, Order, OrderStatus

    async def _go():
        async with session_scope() as s:
            order = Order(
                account_id=account_id,
                status=OrderStatus.VALID,
                identifiers=[{"type": "dns", "value": "x.lan"}],
            )
            s.add(order)
            await s.commit()
            await s.refresh(order)
            record = Certificate(
                order_id=order.id,
                pem_chain=cert.public_bytes(Encoding.PEM).decode(),
                serial=format(cert.serial_number, "x"),
                domains=["x.lan"],
            )
            s.add(record)
            await s.commit()

    asyncio.run(_go())


def _revoke_body(client, cert, *, signer, kid_id=None):
    from cryptography.hazmat.primitives.serialization import Encoding

    protected = {"alg": "RS256", "nonce": _nonce(client), "url": f"{BASE}/acme/revoke-cert"}
    if kid_id:
        protected["kid"] = f"{BASE}/acme/acct/{kid_id}"
    else:
        protected["jwk"] = signer.public_key().to_json()
    der = cert.public_bytes(Encoding.DER)
    return _sign(signer, protected, {"certificate": b64url_encode(der)})


def test_unrelated_account_cannot_revoke_certificate(client):
    owner_id = _register(client, _new_key(), "owner@example.com")
    attacker = _new_key()
    attacker_id = _register(client, attacker, "attacker@example.com")

    cert, _ = _self_signed("x.lan")
    _store_issued_cert(owner_id, cert)

    resp = _post(
        client, "/acme/revoke-cert", _revoke_body(client, cert, signer=attacker, kid_id=attacker_id)
    )
    assert resp.status_code == 401, resp.text


def test_unknown_certificate_cannot_be_revoked(client):
    key = _new_key()
    acct_id = _register(client, key, "owner@example.com")
    cert, _ = _self_signed("never-issued.lan")  # never stored

    body = _revoke_body(client, cert, signer=key, kid_id=acct_id)
    resp = _post(client, "/acme/revoke-cert", body)
    assert resp.status_code == 401, resp.text


def test_owning_account_may_revoke(client, monkeypatch):
    called = {}

    def _fake_revoke(pem, reason):
        called["pem"] = pem

    monkeypatch.setattr("acme_lan.upstream.fulfil.revoke_certificate", _fake_revoke)

    key = _new_key()
    acct_id = _register(client, key, "owner@example.com")
    cert, _ = _self_signed("x.lan")
    _store_issued_cert(acct_id, cert)

    body = _revoke_body(client, cert, signer=key, kid_id=acct_id)
    resp = _post(client, "/acme/revoke-cert", body)
    assert resp.status_code == 200, resp.text
    assert called["pem"].startswith("-----BEGIN CERTIFICATE-----")


def test_certificate_key_holder_may_revoke(client, monkeypatch):
    called = {}
    monkeypatch.setattr(
        "acme_lan.upstream.fulfil.revoke_certificate",
        lambda pem, reason: called.setdefault("pem", pem),
    )

    owner_id = _register(client, _new_key(), "owner@example.com")
    cert, cert_key = _self_signed("x.lan")
    _store_issued_cert(owner_id, cert)

    # Signed with the certificate's own key pair (embedded jwk, no kid) — RFC 8555 §7.6.
    signer = josepy.JWKRSA(key=josepy.ComparableRSAKey(cert_key))
    resp = _post(client, "/acme/revoke-cert", _revoke_body(client, cert, signer=signer))
    assert resp.status_code == 200, resp.text
    assert "pem" in called
