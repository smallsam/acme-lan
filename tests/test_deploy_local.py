"""Tests for the local filesystem deploy plugin."""

from __future__ import annotations

from acme_lan.deploy.base import DeployContext
from acme_lan.deploy.factory import available_plugins, get_deploy_plugin
from acme_lan.deploy.local import LocalDeployPlugin
from acme_lan.models import ManagedHost


def _ctx(config) -> DeployContext:
    return DeployContext(
        host=ManagedHost(name="h", domains=["db.lan.test"], address="127.0.0.1"),
        fullchain_pem="CERTDATA",
        private_key_pem="KEYDATA",
        credential=None,
        config=config,
    )


def test_local_deploy_writes_files(tmp_path):
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    result = LocalDeployPlugin().deploy(
        _ctx({"cert_path": str(cert_path), "key_path": str(key_path)})
    )
    assert result.ok
    assert cert_path.read_text() == "CERTDATA"
    assert key_path.read_text() == "KEYDATA"
    assert (key_path.stat().st_mode & 0o777) == 0o600


def test_local_deploy_runs_reload_command(tmp_path):
    marker = tmp_path / "reloaded"
    result = LocalDeployPlugin().deploy(
        _ctx(
            {
                "cert_path": str(tmp_path / "c.pem"),
                "key_path": str(tmp_path / "k.pem"),
                "reload_command": f"touch {marker}",
            }
        )
    )
    assert result.ok
    assert marker.exists()


def test_local_deploy_missing_config():
    result = LocalDeployPlugin().deploy(_ctx({}))
    assert not result.ok


def test_reload_command_failure_reported(tmp_path):
    result = LocalDeployPlugin().deploy(
        _ctx(
            {
                "cert_path": str(tmp_path / "c.pem"),
                "key_path": str(tmp_path / "k.pem"),
                "reload_command": "exit 3",
            }
        )
    )
    assert not result.ok
    assert "failed" in result.detail


def test_factory_lists_and_builds_plugins():
    assert "local" in available_plugins()
    assert "ssh" in available_plugins()
    assert isinstance(get_deploy_plugin("local"), LocalDeployPlugin)
