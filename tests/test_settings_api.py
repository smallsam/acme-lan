"""Tests for the YAML config layer and the settings API."""

from __future__ import annotations

import os

import httpx
import pytest
import yaml

from acme_lan.settings_schema import NON_SECRET_CREDENTIAL_LIKE, SECRET_FIELDS


@pytest.fixture(autouse=True)
async def _dispose_engine():
    """Dispose the engine on this test's loop so aiosqlite threads don't outlive it."""
    yield
    from acme_lan import db

    await db.reset_engine()


async def _app(tmp_path, **env):
    os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)
    os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_path}/settings.sqlite"
    os.environ["ACME_LAN_CONFIG_FILE"] = str(tmp_path / "config.yml")
    # A .env in the repo root would otherwise outrank the file under test.
    os.environ["ACME_LAN_DOTENV_FILE"] = str(tmp_path / "absent.env")
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


def _find(payload, key):
    for group in payload["groups"]:
        for field in group["fields"]:
            if field["key"] == key:
                return field
    raise AssertionError(f"{key} not present in the settings response")


async def test_every_setting_is_exposed_and_grouped(tmp_path):
    from acme_lan.config import Settings

    app = await _app(tmp_path)
    async with _client(app) as client:
        payload = (await client.get("/api/settings")).json()
    exposed = {f["key"] for g in payload["groups"] for f in g["fields"]}
    # The goal is "all configuration options available in the GUI" — so assert exactly that.
    assert exposed == set(Settings.model_fields)
    assert all(g["title"] for g in payload["groups"])


async def test_writing_settings_persists_to_yaml_and_takes_effect(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        resp = await client.put(
            "/api/settings",
            json={"values": {"dns_provider": "acmedns", "renew_before_days": 45}},
        )
        assert resp.status_code == 200

    written = yaml.safe_load((tmp_path / "config.yml").read_text())
    assert written["dns_provider"] == "acmedns"
    assert written["renew_before_days"] == 45

    # The running process now sees the new values.
    from acme_lan import config

    config.reset_settings_cache()
    assert config.get_settings().dns_provider == "acmedns"
    assert config.get_settings().renew_before_days == 45

    # And a fresh read reports them as coming from the file, still editable.
    async with _client(app) as client:
        field = _find((await client.get("/api/settings")).json(), "dns_provider")
    assert field["source"] == "file"
    assert field["editable"] is True


async def test_env_provided_settings_are_reported_as_enforced_and_rejected(tmp_path):
    app = await _app(tmp_path, ACME_LAN_DNS_PROVIDER="cloudflare")
    async with _client(app) as client:
        payload = (await client.get("/api/settings")).json()
        field = _find(payload, "dns_provider")
        assert field["source"] == "env"
        assert field["editable"] is False
        assert field["env_var"] == "ACME_LAN_DNS_PROVIDER"
        assert payload["enforced_count"] >= 1

        # Attempting to change it must fail loudly rather than write a file that is ignored.
        resp = await client.put("/api/settings", json={"values": {"dns_provider": "acmedns"}})
        assert resp.status_code == 409
        assert "environment variable" in resp.json()["detail"]
    assert not (tmp_path / "config.yml").exists()


async def test_env_beats_the_yaml_file(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"renew_before_days": 45}})

    # Same file, but now the environment also sets it: the environment wins.
    os.environ["ACME_LAN_RENEW_BEFORE_DAYS"] = "7"
    from acme_lan import config

    config.reset_settings_cache()
    assert config.get_settings().renew_before_days == 7
    async with _client(app) as client:
        field = _find((await client.get("/api/settings")).json(), "renew_before_days")
    assert field["value"] == 7
    assert field["editable"] is False


async def test_secrets_are_never_returned_but_can_be_set(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put(
            "/api/settings", json={"values": {"cloudflare_api_token": "cfut_supersecret"}}
        )
        field = _find((await client.get("/api/settings")).json(), "cloudflare_api_token")
        assert field["secret"] is True
        assert field["is_set"] is True
        assert field["value"] == "••••••••"
        assert "supersecret" not in str(field)

        # Sending the mask back must not overwrite the stored secret.
        await client.put(
            "/api/settings", json={"values": {"cloudflare_api_token": "••••••••"}}
        )
    stored = yaml.safe_load((tmp_path / "config.yml").read_text())
    assert stored["cloudflare_api_token"] == "cfut_supersecret"


async def test_unset_reverts_a_setting_to_its_default(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"renew_before_days": 45}})
        await client.put("/api/settings", json={"unset": ["renew_before_days"]})
        field = _find((await client.get("/api/settings")).json(), "renew_before_days")
    assert field["source"] == "default"
    assert field["value"] == 30


async def test_invalid_values_are_rejected_without_touching_the_file(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"renew_before_days": 45}})
        resp = await client.put(
            "/api/settings", json={"values": {"renew_before_days": "not-a-number"}}
        )
        assert resp.status_code == 422
        resp = await client.put("/api/settings", json={"values": {"no_such_setting": 1}})
        assert resp.status_code == 400
    # The earlier good value survived the rejected writes.
    assert yaml.safe_load((tmp_path / "config.yml").read_text())["renew_before_days"] == 45


async def test_malformed_config_file_does_not_break_startup(tmp_path):
    (tmp_path / "config.yml").write_text("this: is: not: valid: yaml:\n\t- broken")
    app = await _app(tmp_path)
    async with _client(app) as client:
        assert (await client.get("/api/settings")).status_code == 200
    from acme_lan import config

    # Falls back to defaults rather than refusing to boot.
    assert config.get_settings().renew_before_days == 30


def test_no_credential_like_field_is_left_unclassified():
    """Guard: a newly added secret must be declared, or this fails."""
    from acme_lan.config import Settings

    suspicious = {
        name
        for name in Settings.model_fields
        if any(word in name for word in ("token", "password", "secret", "key", "credential"))
    }
    unclassified = suspicious - SECRET_FIELDS - NON_SECRET_CREDENTIAL_LIKE
    assert not unclassified, (
        f"classify these in settings_schema.py as secret or non-secret: {sorted(unclassified)}"
    )


@pytest.mark.parametrize(
    ("provider", "tenant", "expected"),
    [
        ("entra", "abc-123", "https://login.microsoftonline.com/abc-123/v2.0/"
                             ".well-known/openid-configuration"),
        ("generic", "abc-123", ""),
    ],
)
def test_entra_discovery_url_is_derived_from_the_tenant_id(provider, tenant, expected):
    from acme_lan.config import Settings

    settings = Settings(oidc_provider=provider, oidc_tenant_id=tenant, oidc_discovery_url="")
    assert settings.oidc_discovery == expected


def _group(payload, group_id):
    return next(g for g in payload["groups"] if g["id"] == group_id)


async def test_dns_section_marks_the_unused_provider_settings(tmp_path):
    """Choosing cloudflare must make it obvious the acme-dns fields aren't used."""
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"dns_provider": "cloudflare"}})
        payload = (await client.get("/api/settings")).json()

    cloudflare = _find(payload, "cloudflare_api_token")
    acmedns = _find(payload, "acmedns_username")
    assert cloudflare["depends_on"]["satisfied"] is True
    assert acmedns["depends_on"]["satisfied"] is False
    assert acmedns["depends_on"]["values"] == ["acmedns"]
    assert acmedns["depends_on"]["label"] == "Provider"
    # Each provider's settings live under their own heading.
    subgroups = [s["title"] for s in _group(payload, "dns")["subgroups"]]
    assert subgroups[0] == ""  # the provider choice itself comes first
    assert "Cloudflare" in subgroups and "acme-dns" in subgroups

    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"dns_provider": "acmedns"}})
        payload = (await client.get("/api/settings")).json()
    assert _find(payload, "cloudflare_api_token")["depends_on"]["satisfied"] is False
    assert _find(payload, "acmedns_username")["depends_on"]["satisfied"] is True


async def test_upstream_section_leads_with_the_challenge_type(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        payload = (await client.get("/api/settings")).json()
    upstream = _group(payload, "upstream")
    # Challenge type is the first option in the section, ungrouped.
    assert upstream["subgroups"][0]["title"] == ""
    assert upstream["subgroups"][0]["fields"][0]["key"] == "upstream_challenge"
    titles = [s["title"] for s in upstream["subgroups"]]
    assert "HTTP-01 (edge)" in titles and "CA account" in titles
    # Edge settings are shown but flagged as unused while dns-01 is selected.
    edge = _find(payload, "edge_public_ip")
    assert edge["depends_on"] == {
        "key": "upstream_challenge",
        "values": ["http-01"],
        "label": "Challenge type",
        "satisfied": False,
    }


async def test_storage_backend_settings_track_the_selected_backend(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        await client.put("/api/settings", json={"values": {"cert_store_backend": "vault"}})
        payload = (await client.get("/api/settings")).json()
    assert _find(payload, "vault_url")["depends_on"]["satisfied"] is True
    assert _find(payload, "azure_keyvault_url")["depends_on"]["satisfied"] is False


async def test_every_field_has_a_label_and_lands_in_a_subgroup(tmp_path):
    app = await _app(tmp_path)
    async with _client(app) as client:
        payload = (await client.get("/api/settings")).json()
    for group in payload["groups"]:
        in_subgroups = {f["key"] for s in group["subgroups"] for f in s["fields"]}
        assert in_subgroups == {f["key"] for f in group["fields"]}, group["id"]
        for entry in group["fields"]:
            assert entry["label"] and not entry["label"].startswith("_")


async def test_options_whose_name_is_not_self_explanatory_carry_help(tmp_path):
    """Guidance where the label alone is ambiguous; nothing redundant where it isn't."""
    app = await _app(tmp_path)
    async with _client(app) as client:
        payload = (await client.get("/api/settings")).json()
    for key in (
        "external_url",
        "auth_required",
        "upstream_challenge",
        "dns_provider",
        "dns_propagation_seconds",
        "secret_key",
        "renew_before_days",
        "health_resolver_overrides",
    ):
        assert _find(payload, key)["help"], f"{key} needs inline help"
    # ...and self-describing ones stay clean.
    assert _find(payload, "acmedns_api_url")["help"] == ""
