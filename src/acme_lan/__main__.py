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
    from .selfcert import ensure_service_certificate, materialize_service_key

    async def _run() -> None:
        await init_db()
        await ensure_service_certificate()

    try:
        asyncio.run(_run())
    except Exception:  # noqa: BLE001 - fall back to HTTP if issuance fails
        logger.warning("Could not obtain service certificate at startup", exc_info=True)

    if not os.path.exists(settings.self_cert_path):
        return None
    # Decrypt the key into an in-memory fd (never a plaintext file on disk).
    key_path = materialize_service_key(settings.service_domain)
    if not key_path:
        return None
    return settings.self_cert_path, key_path


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()

    # Auto-migrate the database to the current release before serving, so upgrading the
    # image transparently upgrades the schema and local data.
    try:
        from .migrate import run_migrations

        run_migrations()
    except Exception:  # noqa: BLE001 - a fresh run still gets tables via init_db()
        logger.warning("Automatic migration failed; continuing with create_all", exc_info=True)
    host = "0.0.0.0"  # noqa: S104 - a LAN service is meant to listen broadly
    port = 8000
    # If external_url encodes a localhost port, honour it for local runs.
    if settings.external_url.startswith(("http://localhost:", "https://localhost:")):
        port = int(settings.external_url.rsplit(":", 1)[1].split("/")[0])

    tls = _bootstrap_service_cert()
    if not tls:
        uvicorn.run("acme_lan.main:app", host=host, port=port, reload=False)
        return

    ssl_certfile, ssl_keyfile = tls
    from . import main as app_module

    https_url = f"https://{settings.service_domain}:{settings.tls_port}"
    app_module.runtime_state.update(tls_active=True, https_url=https_url)
    logger.info(
        "Serving HTTPS on port %s (%s) alongside HTTP on port %s",
        settings.tls_port,
        https_url,
        port,
    )
    https_server = uvicorn.Server(
        uvicorn.Config(
            "acme_lan.main:app",
            host=host,
            port=settings.tls_port,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
    )
    # Same app on plain HTTP; lifespan (init + background tasks) must run exactly once,
    # so only the HTTPS server drives it.
    http_server = uvicorn.Server(
        uvicorn.Config("acme_lan.main:app", host=host, port=port, lifespan="off")
    )

    async def _serve_both() -> None:
        tasks = [
            asyncio.create_task(https_server.serve()),
            asyncio.create_task(http_server.serve()),
        ]
        # If either listener stops (signal or crash), shut the other down too.
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        https_server.should_exit = True
        http_server.should_exit = True
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(_serve_both())


if __name__ == "__main__":
    main()
