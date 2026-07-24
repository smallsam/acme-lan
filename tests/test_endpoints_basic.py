"""Endpoint-level tests that don't require JWS signing (directory, nonce, error paths)."""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    os.environ["ACME_LAN_EXTERNAL_URL"] = "http://localhost:8000"
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/basic.sqlite"
    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None
    from acme_lan.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_directory_lists_all_resources(client):
    body = client.get("/acme/directory").json()
    for key in ("newNonce", "newAccount", "newOrder", "revokeCert", "keyChange"):
        assert body[key].startswith("http://localhost:8000/acme/")


def test_new_nonce_head_and_get_carry_replay_nonce(client):
    head = client.head("/acme/new-nonce")
    assert head.status_code == 200
    assert head.headers["Replay-Nonce"]

    get = client.get("/acme/new-nonce")
    assert get.status_code == 204
    assert get.headers["Replay-Nonce"]
    assert get.headers["Cache-Control"] == "no-store"


def test_new_nonces_are_unique(client):
    seen = {client.get("/acme/new-nonce").headers["Replay-Nonce"] for _ in range(5)}
    assert len(seen) == 5


def test_wrong_content_type_is_rejected(client):
    resp = client.post("/acme/new-account", content=b"{}", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.json()["type"].endswith(":malformed")


def test_non_jws_body_is_malformed(client):
    resp = client.post(
        "/acme/new-account",
        content=b"not json",
        headers={"Content-Type": "application/jose+json"},
    )
    assert resp.status_code == 400
    problem = resp.json()
    assert problem["type"].endswith(":malformed")
    # Every ACME response, including errors, must supply a fresh nonce.
    assert resp.headers["Replay-Nonce"]
