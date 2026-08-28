"""On-disk YAML configuration, editable from the dashboard.

Configuration comes from three places, highest priority first:

1. **Environment variables** (``ACME_LAN_*``) and ``.env``. These are how a container is
   configured, so they win — and because the dashboard cannot change a process's
   environment, any option set this way is reported as *enforced* and rendered read-only.
2. **This YAML file** (``ACME_LAN_CONFIG_FILE``, default ``./data/config.yml``), which is
   what the dashboard writes.
3. The field defaults in :mod:`acme_lan.config`.

Keys in the file are the setting names without the ``ACME_LAN_`` prefix and in lower case,
e.g. ``dns_provider: cloudflare``.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

CONFIG_FILE_ENV = "ACME_LAN_CONFIG_FILE"
DEFAULT_CONFIG_FILE = "./data/config.yml"
ENV_PREFIX = "ACME_LAN_"


def config_file_path() -> Path:
    """Where the editable configuration lives."""
    return Path(os.environ.get(CONFIG_FILE_ENV) or DEFAULT_CONFIG_FILE)


def load_config_file(path: Path | None = None) -> dict[str, Any]:
    """Read the YAML config, or an empty mapping if it is missing/blank/unreadable."""
    target = path or config_file_path()
    try:
        raw = target.read_text()
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return {}
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def save_config_file(values: dict[str, Any], path: Path | None = None) -> Path:
    """Write the YAML config atomically, so a crash can't leave a half-written file."""
    target = path or config_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(dict(sorted(values.items())), default_flow_style=False, sort_keys=True)
    header = (
        "# acme-lan configuration, managed from the dashboard.\n"
        "# Environment variables (ACME_LAN_*) override anything set here.\n"
    )
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".config-", suffix=".yml")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(header + body)
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise
    # Config can hold provider tokens; keep it owner-readable only.
    with contextlib.suppress(OSError):
        os.chmod(target, 0o600)
    return target


def env_set_keys(field_names: set[str]) -> dict[str, str]:
    """Map setting name -> which environment layer defines it (``env`` or ``dotenv``).

    Anything listed here outranks the YAML file, so the UI must present it as enforced.
    """
    found: dict[str, str] = {}
    upper_env = {key.upper() for key in os.environ}
    for name in field_names:
        if f"{ENV_PREFIX}{name}".upper() in upper_env:
            found[name] = "env"
    # A .env file is loaded by pydantic-settings above the YAML source too.
    dotenv = Path(os.environ.get("ACME_LAN_DOTENV_FILE", ".env"))
    try:
        lines = dotenv.read_text().splitlines()
    except OSError:
        return found
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip().upper()
        if not key.startswith(ENV_PREFIX):
            continue
        name = key[len(ENV_PREFIX) :].lower()
        if name in field_names and name not in found:
            found[name] = "dotenv"
    return found


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """pydantic-settings source backed by :func:`load_config_file`."""

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data = load_config_file()

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        known = set(self.settings_cls.model_fields)
        return {
            key: value
            for key, value in self._data.items()
            if key in known and value is not None
        }
