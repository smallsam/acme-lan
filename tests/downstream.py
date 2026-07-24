"""Helpers that drive the real ``acme`` client library against a live acme-lan server."""

from __future__ import annotations

import josepy
from acme import challenges, client, messages
from cryptography.hazmat.primitives.asymmetric import rsa

from acme_lan.config import get_settings


def build_downstream_client(base_url: str) -> tuple[client.ClientV2, josepy.JWKRSA]:
    """Register an account against the acme-lan server and return (client, account_key)."""
    account_key = josepy.JWKRSA(key=josepy.ComparableRSAKey(
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ))
    net = client.ClientNetwork(account_key, user_agent="acme-lan-tests")
    directory = client.ClientV2.get_directory(f"{base_url}/acme/directory", net)
    acme_client = client.ClientV2(directory, net=net)
    regr = acme_client.new_account(
        messages.NewRegistration.from_data(
            email="tester@example.com", terms_of_service_agreed=True
        )
    )
    net.account = regr
    return acme_client, account_key


def _http01(authz: messages.AuthorizationResource) -> messages.ChallengeBody:
    for challb in authz.body.challenges:
        if isinstance(challb.chall, challenges.HTTP01):
            return challb
    raise AssertionError("no http-01 challenge offered")


def answer_http01_challenges(
    acme_client: client.ClientV2,
    account_key: josepy.JWKRSA,
    orderr: messages.OrderResource,
    responder,
) -> None:
    """Serve and answer the http-01 challenge for every authorization in the order."""
    settings = get_settings()
    for authz in orderr.authorizations:
        challb = _http01(authz)
        response, validation = challb.chall.response_and_validation(account_key)
        token = challb.chall.encode("token")
        responder.register(token, validation)
        # Point the server's validator at our local responder for this identifier.
        settings.http01_resolver_overrides[authz.body.identifier.value] = (
            f"127.0.0.1:{responder.port}"
        )
        acme_client.answer_challenge(challb, response)
