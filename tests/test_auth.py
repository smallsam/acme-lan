"""Tests for local login, sessions, user administration and the OIDC flow."""

from __future__ import annotations

import os
import time

import httpx
import pytest

from acme_lan.oidc import OidcError, decode_jwt_claims, make_pkce, validate_claims
from acme_lan.users import SESSION_COOKIE, hash_password, verify_password


@pytest.fixture(autouse=True)
async def _dispose_engine():
    yield
    from acme_lan import db

    await db.reset_engine()


async def _app(tmp_path, **env):
    for key in ("ACME_LAN_ADMIN_TOKEN", "ACME_LAN_AUTH_REQUIRED", "ACME_LAN_OIDC_ENABLED"):
        os.environ.pop(key, None)
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/auth.sqlite"
    os.environ["ACME_LAN_CONFIG_FILE"] = str(tmp_path / "config.yml")
    os.environ["ACME_LAN_DOTENV_FILE"] = str(tmp_path / "absent.env")
    os.environ["ACME_LAN_EXTERNAL_URL"] = "http://localhost:8000"
    for key, value in env.items():
        os.environ[key] = value

    from acme_lan import config, db

    config.reset_settings_cache()
    db._engine = None
    db._sessionmaker = None
    from acme_lan.db import init_db

    await init_db()
    from acme_lan.main import create_app

    return create_app()


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# --- password hashing ---


def test_password_hash_round_trips_and_rejects_wrong_input():
    stored = hash_password("correct horse battery staple", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert "correct horse" not in stored  # the plaintext is not recoverable from the hash
    assert verify_password("correct horse battery staple", stored) is True
    assert verify_password("wrong", stored) is False
    assert verify_password("", stored) is False


def test_two_hashes_of_the_same_password_differ():
    """Salted: identical passwords must not produce identical hashes."""
    assert hash_password("same", iterations=1000) != hash_password("same", iterations=1000)


def test_verify_password_tolerates_garbage_hashes():
    for junk in ("", "not-a-hash", "pbkdf2_sha256$abc$def$ghi", "md5$1$x$y"):
        assert verify_password("whatever", junk) is False


# --- first-run setup and local login ---


async def test_setup_creates_the_first_user_then_refuses(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        status = (await client.get("/api/auth/status")).json()
        assert status["needs_setup"] is True
        assert status["local_login_enabled"] is False

        resp = await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        assert resp.status_code == 201
        assert resp.cookies.get(SESSION_COOKIE)

        # Second attempt is refused — this endpoint is only for bootstrapping.
        again = await client.post(
            "/api/auth/setup", json={"username": "eve", "password": "hunter2hunter2"}
        )
        assert again.status_code == 409

        status = (await client.get("/api/auth/status")).json()
        assert status["needs_setup"] is False
        assert status["user"]["username"] == "sam"


async def test_short_passwords_are_rejected(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        resp = await client.post("/api/auth/setup", json={"username": "s", "password": "short"})
        assert resp.status_code == 422


async def test_login_logout_cycle(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        await client.post("/api/auth/logout")
        assert (await client.get("/api/auth/status")).json()["user"] is None

        bad = await client.post(
            "/api/auth/login", json={"username": "sam", "password": "wrong-password"}
        )
        assert bad.status_code == 401

        good = await client.post(
            "/api/auth/login", json={"username": "sam", "password": "hunter2hunter2"}
        )
        assert good.status_code == 200
        assert (await client.get("/api/auth/status")).json()["user"]["username"] == "sam"


async def test_auth_required_gates_the_management_api(tmp_path):
    app = await _app(tmp_path, ACME_LAN_AUTH_REQUIRED="true")
    async with _client(app) as client:
        # Locked out until logged in...
        assert (await client.get("/api/stats")).status_code == 401
        # ...but ACME endpoints are never gated: clients authenticate per RFC 8555.
        assert (await client.get("/acme/directory")).status_code == 200

        await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        assert (await client.get("/api/stats")).status_code == 200

        await client.post("/api/auth/logout")
        assert (await client.get("/api/stats")).status_code == 401


async def test_admin_token_still_works_alongside_sessions(tmp_path):
    app = await _app(tmp_path, ACME_LAN_ADMIN_TOKEN="s3cret", ACME_LAN_AUTH_REQUIRED="true")
    async with _client(app) as client:
        assert (await client.get("/api/stats")).status_code == 401
        ok = await client.get("/api/stats", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
        bad = await client.get("/api/stats", headers={"Authorization": "Bearer nope"})
        assert bad.status_code == 401


async def test_disabling_a_user_revokes_their_session_immediately(tmp_path):
    app = await _app(tmp_path, ACME_LAN_AUTH_REQUIRED="true")
    async with _client(app) as client:
        created = await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        user_id = created.json()["user"]["id"]
        # Add a second admin so the first can be disabled without locking everyone out.
        await client.post(
            "/api/users", json={"username": "other", "password": "hunter2hunter2"}
        )
        assert (await client.get("/api/stats")).status_code == 200

        await client.patch(f"/api/users/{user_id}", json={"disabled": True})
        # Sessions are server-side rows, so this takes effect at once.
        assert (await client.get("/api/stats")).status_code == 401


async def test_password_change_invalidates_existing_sessions(tmp_path):
    app = await _app(tmp_path, ACME_LAN_AUTH_REQUIRED="true")
    async with _client(app) as client:
        created = await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        user_id = created.json()["user"]["id"]
        await client.patch(f"/api/users/{user_id}", json={"password": "brand-new-password"})
        assert (await client.get("/api/stats")).status_code == 401
        again = await client.post(
            "/api/auth/login", json={"username": "sam", "password": "brand-new-password"}
        )
        assert again.status_code == 200


async def test_last_user_cannot_be_deleted(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        created = await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        user_id = created.json()["user"]["id"]
        resp = await client.delete(f"/api/users/{user_id}")
        assert resp.status_code == 409
        assert "locked out" in resp.json()["detail"]


async def test_duplicate_usernames_are_refused(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        resp = await client.post(
            "/api/users", json={"username": "SAM", "password": "hunter2hunter2"}
        )
        assert resp.status_code == 409


async def test_users_never_expose_password_hashes(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.post(
            "/api/auth/setup", json={"username": "sam", "password": "hunter2hunter2"}
        )
        listed = (await client.get("/api/users")).json()
    assert listed[0]["has_password"] is True
    assert "password_hash" not in listed[0]
    assert "hunter2" not in str(listed)


# --- OIDC ---


def test_pkce_challenge_is_the_s256_of_the_verifier():
    import base64
    import hashlib

    verifier, challenge = make_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    assert challenge == expected
    assert "=" not in challenge  # base64url, unpadded, per RFC 7636


def _id_token(claims: dict) -> str:
    import base64
    import json

    def seg(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'RS256'})}.{seg(claims)}.signature-not-checked"


def test_decode_jwt_claims_reads_the_payload():
    token = _id_token({"sub": "user-1", "email": "sam@example.com"})
    assert decode_jwt_claims(token)["email"] == "sam@example.com"
    with pytest.raises(OidcError):
        decode_jwt_claims("not-a-jwt")


def test_validate_claims_accepts_a_good_token():
    now = int(time.time())
    validate_claims(
        {"iss": "https://idp.test", "aud": "client-1", "exp": now + 300, "nonce": "n1"},
        issuer="https://idp.test",
        client_id="client-1",
        nonce="n1",
        now=now,
    )


@pytest.mark.parametrize(
    ("claims", "message"),
    [
        ({"iss": "https://evil.test", "aud": "client-1", "exp": 9999999999, "nonce": "n1"},
         "issuer"),
        ({"iss": "https://idp.test", "aud": "other", "exp": 9999999999, "nonce": "n1"},
         "audience"),
        ({"iss": "https://idp.test", "aud": "client-1", "exp": 1, "nonce": "n1"}, "expired"),
        ({"iss": "https://idp.test", "aud": "client-1", "exp": 9999999999, "nonce": "wrong"},
         "nonce"),
    ],
)
def test_validate_claims_rejects_tampered_tokens(claims, message):
    with pytest.raises(OidcError, match=message):
        validate_claims(
            claims, issuer="https://idp.test", client_id="client-1", nonce="n1",
            now=int(time.time()),
        )


def test_validate_claims_handles_entra_multitenant_issuer_placeholder():
    now = int(time.time())
    validate_claims(
        {
            "iss": "https://login.microsoftonline.com/tenant-abc/v2.0",
            "tid": "tenant-abc",
            "aud": "client-1",
            "exp": now + 300,
            "nonce": "n1",
        },
        issuer="https://login.microsoftonline.com/{tenantid}/v2.0",
        client_id="client-1",
        nonce="n1",
        now=now,
    )


def test_validate_claims_accepts_a_list_audience():
    now = int(time.time())
    validate_claims(
        {"iss": "https://idp.test", "aud": ["other", "client-1"], "exp": now + 300},
        issuer="https://idp.test",
        client_id="client-1",
        nonce="",
        now=now,
    )


async def test_oidc_status_and_redirect_uri(tmp_path):
    app = await _app(
        tmp_path,
        ACME_LAN_OIDC_ENABLED="true",
        ACME_LAN_OIDC_PROVIDER="entra",
        ACME_LAN_OIDC_TENANT_ID="tenant-abc",
        ACME_LAN_OIDC_CLIENT_ID="client-1",
    )
    async with _client(app) as client:
        status = (await client.get("/api/auth/status")).json()
    assert status["oidc_enabled"] is True
    assert status["oidc_provider"] == "entra"
    # The exact value to paste into the Entra app registration.
    assert status["oidc_redirect_uri"] == "http://localhost:8000/api/auth/oidc/callback"


async def test_oidc_start_requires_configuration(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        resp = await client.get("/api/auth/oidc/start")
    assert resp.status_code == 400


async def test_oidc_callback_rejects_an_unknown_state(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        resp = await client.get(
            "/api/auth/oidc/callback?code=abc&state=never-issued",
            follow_redirects=False,
        )
    # Failures go back to the dashboard with a reason rather than a bare error page.
    assert resp.status_code in (302, 307)
    assert "login_error" in resp.headers["location"]


async def test_oidc_callback_surfaces_provider_errors(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        resp = await client.get(
            "/api/auth/oidc/callback?error=access_denied&error_description=User+declined",
            follow_redirects=False,
        )
    assert "access_denied" in resp.headers["location"]


async def test_enabling_auth_with_no_users_still_allows_first_run_setup(tmp_path):
    """Turning on Require login before creating an account must not lock anyone out."""
    app = await _app(tmp_path, ACME_LAN_AUTH_REQUIRED="true")
    async with _client(app) as client:
        # The management API is closed...
        assert (await client.get("/api/stats")).status_code == 401
        # ...but status and the bootstrap endpoint remain reachable, so the UI can offer
        # to create the first administrator.
        status = (await client.get("/api/auth/status")).json()
        assert status["needs_setup"] is True
        created = await client.post(
            "/api/auth/setup", json={"username": "rescue", "password": "hunter2hunter2"}
        )
        assert created.status_code == 201
        assert (await client.get("/api/stats")).status_code == 200
