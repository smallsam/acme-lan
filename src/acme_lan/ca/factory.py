"""Registry / factory for private-CA handlers (acme2certifier-style plugins).

Additional handlers (e.g. adapted acme2certifier ``ca_handler`` modules for Microsoft
ADCS, EJBCA, XCA, …) register here under a name and become selectable by any listener
profile with ``upstream_type=ca_handler``.
"""

from __future__ import annotations

from .base import CaHandler
from .local_ca import LocalCaHandler

_HANDLERS: dict[str, type[CaHandler]] = {
    LocalCaHandler.name: LocalCaHandler,
}


def register_ca_handler(handler_cls: type[CaHandler]) -> None:
    _HANDLERS[handler_cls.name] = handler_cls


def available_ca_handlers() -> list[str]:
    return sorted(_HANDLERS)


def get_ca_handler(name: str, config: dict | None = None) -> CaHandler:
    try:
        return _HANDLERS[name](config)
    except KeyError as exc:
        raise ValueError(
            f"Unknown ca_handler {name!r}; available: {', '.join(available_ca_handlers())}"
        ) from exc
