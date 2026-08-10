"""Registry / factory for deploy plugins."""

from __future__ import annotations

from .base import DeployPlugin
from .cisco_ios import CiscoIosDeployPlugin
from .local import LocalDeployPlugin
from .ssh import SshDeployPlugin

_PLUGINS: dict[str, type[DeployPlugin]] = {
    CiscoIosDeployPlugin.name: CiscoIosDeployPlugin,
    LocalDeployPlugin.name: LocalDeployPlugin,
    SshDeployPlugin.name: SshDeployPlugin,
}


def register_plugin(plugin_cls: type[DeployPlugin]) -> None:
    """Register a deploy plugin class under its ``name`` (for extensions / tests)."""
    _PLUGINS[plugin_cls.name] = plugin_cls


def available_plugins() -> list[str]:
    return sorted(_PLUGINS)


def plugin_specs() -> list[dict]:
    """Describe each plugin (name, whether it supports device CSRs, and its config fields)."""
    from dataclasses import asdict

    specs = []
    for name in available_plugins():
        cls = _PLUGINS[name]
        specs.append(
            {
                "name": name,
                "supports_csr_retrieval": cls.supports_csr_retrieval,
                "fields": [asdict(f) for f in cls.fields],
            }
        )
    return specs


def get_deploy_plugin(name: str) -> DeployPlugin:
    try:
        return _PLUGINS[name]()
    except KeyError as exc:
        raise ValueError(
            f"Unknown deploy plugin {name!r}; available: {', '.join(available_plugins())}"
        ) from exc
