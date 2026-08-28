"""Parsing and verification of ACME request JWS objects (RFC 8555 §6.2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import josepy
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import Account
from .encoding import b64url_decode, b64url_encode
from .errors import bad_nonce, malformed, unauthorized
from .nonce import consume_nonce

# alg -> (hash, is_ec, ec_component_len)
_RSA_ALGS = {"RS256": hashes.SHA256(), "RS384": hashes.SHA384(), "RS512": hashes.SHA512()}
_EC_ALGS = {
    "ES256": (hashes.SHA256(), 32),
    "ES384": (hashes.SHA384(), 48),
    "ES512": (hashes.SHA512(), 66),
}


@dataclass
class VerifiedRequest:
    """The result of successfully verifying an inbound ACME JWS."""

    payload: dict[str, Any] | None  # None for POST-as-GET (empty payload)
    protected: dict[str, Any]
    account_id: str | None
    account: Account | None
    jwk: josepy.JWK  # public key that signed the request
    jwk_dict: dict[str, Any]

    @property
    def is_post_as_get(self) -> bool:
        return self.payload is None

    def thumbprint_b64(self) -> str:
        """base64url(SHA-256 JWK thumbprint) — the account-key half of a keyAuthorization."""
        return b64url_encode(self.jwk.thumbprint())


def _verify_signature(
    jwk: josepy.JWK, kty: str, alg: str, signing_input: bytes, signature: bytes
) -> None:
    key = jwk.key  # josepy ComparableKey; delegates to the cryptography key
    try:
        if kty == "RSA":
            if alg not in _RSA_ALGS:
                raise malformed(f"Unsupported RSA alg {alg}")
            key.verify(signature, signing_input, padding.PKCS1v15(), _RSA_ALGS[alg])
        elif kty == "EC":
            if alg not in _EC_ALGS:
                raise malformed(f"Unsupported EC alg {alg}")
            digest, comp_len = _EC_ALGS[alg]
            if len(signature) != comp_len * 2:
                raise malformed("Malformed ECDSA signature length")
            r = int.from_bytes(signature[:comp_len], "big")
            s = int.from_bytes(signature[comp_len:], "big")
            der = encode_dss_signature(r, s)
            key.verify(der, signing_input, ec.ECDSA(digest))
        else:
            raise malformed(f"Unsupported key type {kty}")
    except InvalidSignature as exc:
        raise unauthorized("JWS signature verification failed") from exc


async def verify_jws(
    request: Request,
    body: bytes,
    session: AsyncSession,
    *,
    expected_url: str | None = None,
) -> VerifiedRequest:
    """Fully validate an ACME JWS request body and return the decoded result.

    Performs: structural parsing, nonce consumption, url binding, key resolution
    (embedded ``jwk`` or account ``kid``), and cryptographic signature verification.
    """
    if not body:
        raise malformed("Empty request body")
    try:
        obj = json.loads(body)
    except ValueError as exc:
        raise malformed("Request body is not valid JSON") from exc

    if not isinstance(obj, dict) or not {"protected", "payload", "signature"} <= obj.keys():
        raise malformed("Request is not a valid flattened JWS")

    protected_b64 = obj["protected"]
    payload_b64 = obj["payload"]
    signature_b64 = obj["signature"]

    try:
        protected = json.loads(b64url_decode(protected_b64))
        signature = b64url_decode(signature_b64)
    except (ValueError, KeyError) as exc:
        raise malformed("Could not decode JWS protected header or signature") from exc
    if not isinstance(protected, dict):
        raise malformed("JWS protected header is not an object")

    alg = protected.get("alg")
    if alg == "none" or not isinstance(alg, str):
        raise malformed("Missing or unacceptable JWS alg")

    # url binding (RFC 8555 §6.4) — the signed url must match where the request landed.
    signed_url = protected.get("url")
    actual_url = expected_url or (get_settings().external_url.rstrip("/") + request.url.path)
    if signed_url != actual_url:
        raise unauthorized(f"JWS url {signed_url!r} does not match request url {actual_url!r}")

    # Anti-replay nonce.
    nonce = protected.get("nonce")
    if not nonce or not isinstance(nonce, str):
        raise bad_nonce("Missing anti-replay nonce")
    await consume_nonce(nonce)

    # Key resolution: exactly one of jwk / kid.
    header_jwk = protected.get("jwk")
    kid = protected.get("kid")
    if bool(header_jwk) == bool(kid):
        raise malformed("JWS must contain exactly one of 'jwk' or 'kid'")

    account: Account | None = None
    account_id: str | None = None
    if header_jwk:
        jwk_dict = header_jwk
    else:
        account_id = kid.rstrip("/").rsplit("/", 1)[-1]
        account = await session.get(Account, account_id)
        if account is None:
            raise unauthorized("Unknown account key identifier")
        # RFC 8555 §7.3.6: a deactivated account may not perform further operations.
        if account.status != "valid":
            raise unauthorized(f"Account is {account.status}")
        jwk_dict = account.jwk

    try:
        jwk = josepy.JWK.from_json(jwk_dict)
    except Exception as exc:  # noqa: BLE001 - surface any josepy parse failure as malformed
        raise malformed("Could not parse JWK") from exc

    kty = jwk_dict.get("kty", "")
    signing_input = (protected_b64 + "." + payload_b64).encode("ascii")
    _verify_signature(jwk, kty, alg, signing_input, signature)

    # Decode payload (empty string == POST-as-GET).
    if payload_b64 == "":
        payload: dict[str, Any] | None = None
    else:
        try:
            payload = json.loads(b64url_decode(payload_b64))
        except ValueError as exc:
            raise malformed("JWS payload is not valid JSON") from exc

    return VerifiedRequest(
        payload=payload,
        protected=protected,
        account_id=account_id,
        account=account,
        jwk=jwk,
        jwk_dict=jwk_dict,
    )
