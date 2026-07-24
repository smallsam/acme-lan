"""Downstream ACME flow against a live acme-lan server (no upstream / no Docker needed).

Exercises account registration, order creation, challenge issuance and http-01 validation
up to the point where the order is ready to finalize.
"""

from __future__ import annotations

import pytest
from acme import client, errors, messages

from .conftest import make_csr
from .downstream import answer_http01_challenges, build_downstream_client


def test_account_order_and_http01_validation(make_server, challenge_responder):
    base = make_server()
    acme_client, account_key = build_downstream_client(base)

    domains = ["db.lan.test"]
    csr_pem, _key = make_csr(domains)
    orderr = acme_client.new_order(csr_pem)

    assert orderr.body.status == messages.STATUS_PENDING
    assert len(orderr.authorizations) == 1
    identifier = orderr.authorizations[0].body.identifier
    assert identifier.value == "db.lan.test"

    answer_http01_challenges(acme_client, account_key, orderr, challenge_responder)

    # Poll the authorization: our server validates http-01 synchronously, so it is valid.
    updated, _resp = acme_client.poll(orderr.authorizations[0])
    assert updated.body.status == messages.STATUS_VALID


def test_account_is_reused_for_same_key(make_server):
    base = make_server()
    acme_client, account_key = build_downstream_client(base)
    first_uri = acme_client.net.account.uri

    # A brand-new client using the SAME account key (jwk-signed newAccount) must be
    # matched to the existing account by its key thumbprint.
    net = client.ClientNetwork(account_key, user_agent="reuse-test")
    directory = client.ClientV2.get_directory(f"{base}/acme/directory", net)
    fresh_client = client.ClientV2(directory, net=net)
    # An existing account is signalled by the CA returning 200 + Location; the acme
    # library raises ConflictError carrying that same account URL.
    with pytest.raises(errors.ConflictError) as exc:
        fresh_client.new_account(
            messages.NewRegistration.from_data(
                email="tester@example.com", terms_of_service_agreed=True
            )
        )
    assert exc.value.location == first_uri
