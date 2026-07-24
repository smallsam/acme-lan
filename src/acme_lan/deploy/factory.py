"""Registry / factory for deploy plugins."""

from __future__ import annotations

from .base import DeployPlugin
from .local import LocalDeployPlugin
from .ssh import SshDeployPlugin

_PLUGINS: dict[str, type[DeployPlugin]] = {
    LocalDeployPlugin.name: LocalDeployPlugin,
    SshDeployPlugin.name: SshDeployPlugin,
}


def available_plugins() -> list[str]:
    return sorted(_PLUGINS)


def get_deploy_plugin(name: str) -> DeployPlugin:
    try:
        return _PLUGINS[name]()
    except KeyError as exc:
        raise ValueError(
            f"Unknown deploy plugin {name!r}; available: {', '.join(available_plugins())}"
        ) from exc
