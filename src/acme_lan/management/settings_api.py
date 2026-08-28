"""Read and edit configuration from the dashboard.

Every setting in :class:`acme_lan.config.Settings` is exposed here, annotated with where its
current value comes from. Options provided by the environment are returned as
``editable: false`` with ``source: "env"`` — the dashboard writes a YAML file, and no file
can override a process's environment, so presenting them as editable would be a lie.

Secret values are never returned; the response says only whether one is set.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticUndefined

from ..config import Settings, get_settings, reset_settings_cache
from ..configfile import config_file_path, env_set_keys, load_config_file, save_config_file
from ..settings_schema import (
    CHOICES,
    FIELD_META,
    GROUPS,
    field_label,
    is_secret,
    meta_for,
    subgroup_order,
)
from .auth import require_admin

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])

MASK = "••••••••"


def _field_type(annotation: Any, name: str) -> str:
    if is_secret(name):
        return "password"
    if name in CHOICES:
        return "select"
    text = str(annotation)
    if "bool" in text:
        return "boolean"
    if "int" in text:
        return "integer"
    if "float" in text:
        return "number"
    if "dict" in text:
        return "json"
    return "text"


def _default_of(field: Any) -> Any:
    """The field's default, resolving default_factory (dict/list fields use one)."""
    if field.default is not PydanticUndefined:
        return field.default
    if field.default_factory is not None:
        return field.default_factory()
    return None


def _describe() -> dict[str, Any]:
    settings = get_settings()
    fields = Settings.model_fields
    enforced = env_set_keys(set(fields))
    stored = load_config_file()

    described: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id, _, _ in GROUPS}
    # Iterate FIELD_META order first so each section lists its options in the order they
    # are meant to be read (challenge type before the settings that depend on it), then
    # pick up anything not yet described.
    ordered = [name for name in FIELD_META if name in fields]
    ordered += [name for name in fields if name not in FIELD_META]

    for name in ordered:
        field = fields[name]
        meta = meta_for(name)
        value = getattr(settings, name)
        secret = is_secret(name)
        source = enforced.get(name) or ("file" if name in stored else "default")
        depends_on = None
        if meta.depends_on:
            dependency, values = meta.depends_on
            depends_on = {
                "key": dependency,
                "values": list(values),
                "label": field_label(dependency),
                # Resolved server-side too, so the "not in use" state is correct on load.
                "satisfied": str(getattr(settings, dependency, "")) in values,
            }
        entry: dict[str, Any] = {
            "key": name,
            "env_var": f"ACME_LAN_{name.upper()}",
            "label": meta.label or field_label(name),
            "subgroup": meta.subgroup,
            # Curated guidance wins over the pydantic description when both exist.
            "help": meta.help or field.description or "",
            "type": _field_type(field.annotation, name),
            "choices": CHOICES.get(name),
            "depends_on": depends_on,
            "source": source,
            # Enforced by the environment => the dashboard must not offer to change it.
            "editable": name not in enforced,
            "secret": secret,
            "is_set": bool(value) if secret else None,
            "value": MASK if (secret and value) else (None if secret else value),
            "default": None if secret else _default_of(field),
        }
        described.setdefault(meta.group, []).append(entry)

    groups = []
    for gid, title, description in GROUPS:
        entries = described.get(gid, [])
        titles = subgroup_order(gid)
        # Any subgroup used by a field but not in the declared order (e.g. a field added
        # without metadata) still gets rendered, at the end.
        for entry in entries:
            if entry["subgroup"] not in titles:
                titles.append(entry["subgroup"])
        groups.append(
            {
                "id": gid,
                "title": title,
                "description": description,
                "fields": entries,
                "subgroups": [
                    {
                        "title": subtitle,
                        "fields": [e for e in entries if e["subgroup"] == subtitle],
                    }
                    for subtitle in titles
                    if any(e["subgroup"] == subtitle for e in entries)
                ],
            }
        )

    return {
        "config_file": str(config_file_path()),
        "config_file_exists": config_file_path().exists(),
        "enforced_count": len(enforced),
        "groups": groups,
    }


@router.get("")
async def read_settings() -> dict[str, Any]:
    return _describe()


class SettingsUpdate(BaseModel):
    # Partial update: only the keys present are changed. Secrets the user didn't retype are
    # simply absent, so they keep their stored value.
    values: dict[str, Any] = {}
    # Keys to drop from the file, reverting them to their built-in default.
    unset: list[str] = []


@router.put("")
async def write_settings(body: SettingsUpdate) -> dict[str, Any]:
    fields = Settings.model_fields
    enforced = env_set_keys(set(fields))

    touched = set(body.values) | set(body.unset)
    unknown = sorted(touched - set(fields))
    if unknown:
        raise HTTPException(400, f"Unknown setting(s): {', '.join(unknown)}")

    blocked = sorted(key for key in touched if key in enforced)
    if blocked:
        raise HTTPException(
            409,
            f"{', '.join(blocked)} is set by an environment variable and cannot be changed "
            "here; edit the environment instead.",
        )
    # A masked value coming back unchanged must not overwrite the real secret.
    incoming = {k: v for k, v in body.values.items() if not (is_secret(k) and v == MASK)}

    stored = load_config_file()
    merged = {k: v for k, v in stored.items() if k in fields}
    merged.update(incoming)
    for key in body.unset:
        merged.pop(key, None)

    # Validate the whole result before writing, so a bad value can't break startup. The
    # environment still participates, matching what the running process will actually see.
    try:
        Settings(**merged)
    except ValidationError as exc:
        raise HTTPException(422, f"Invalid configuration: {exc.errors()[0]['msg']}") from exc

    try:
        save_config_file(merged)
    except OSError as exc:
        raise HTTPException(500, f"Could not write {config_file_path()}: {exc}") from exc
    reset_settings_cache()
    return _describe()
