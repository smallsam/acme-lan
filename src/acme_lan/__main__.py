"""Console entrypoint: ``acme-lan`` runs the server with uvicorn."""

from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from .config import get_settings

logger = logging.getLogger("acme_lan")


def _bootstrap_service_cert() -> tuple[str, str] | None:
    """Obtain the service certificate before serving, so HTTPS can start immediately."""
    settings = get_settings()
    if not (settings.self_cert_enabled and settings.service_domain):
        return None

    from .db import init_db
    from .selfcert import ensure_service_certificate

    async def _run() -> None:
        await init_db()
        await ensure_service_certificate()

    try:
        asyncio.run(_run())
    except Exception:  # noqa: BLE001 - fall back to HTTP if issuance fails
        logger.warning("Could not obtain service certificate at startup", exc_info=True)

    if os.path.exists(settings.self_cert_path) and os.path.exists(settings.self_cert_key_path):
        return settings.self_cert_path, settings.self_cert_key_path
    return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    host = "0.0.0.0"  # noqa: S104 - a LAN service is meant to listen broadly
    port = 8000
    # If external_url encodes a localhost port, honour it for local runs.
    if settings.external_url.startswith(("http://localhost:", "https://localhost:")):
        port = int(settings.external_url.rsplit(":", 1)[1].split("/")[0])

    tls = _bootstrap_service_cert()
    ssl_certfile, ssl_keyfile = tls if tls else (None, None)
    if tls:
        logger.info("Serving HTTPS with the acme-lan service certificate")

    uvicorn.run(
        "acme_lan.main:app",
        host=host,
        port=port,
        reload=False,
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


if __name__ == "__main__":
    main()
