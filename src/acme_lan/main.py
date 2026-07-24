"""FastAPI application factory for the acme-lan server."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .acme import accounts, authz, certificates, directory, orders
from .acme.errors import AcmeError, acme_error_handler
from .config import get_settings
from .db import init_db
from .management import api as management_api
from .management import hosts_api
from .notifications import get_channels, run_notifier
from .scheduler import run_scheduler

FRONTEND_DIST = Path(__file__).resolve().parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    settings = get_settings()
    stop_event = asyncio.Event()
    tasks: list[asyncio.Task] = []
    if settings.auto_renew_enabled:
        tasks.append(asyncio.create_task(run_scheduler(stop_event)))
    if get_channels(settings):
        tasks.append(asyncio.create_task(run_notifier(stop_event)))
    try:
        yield
    finally:
        stop_event.set()
        for task in tasks:
            await task


def create_app() -> FastAPI:
    app = FastAPI(
        title="acme-lan",
        version="0.1.0",
        description="Internal ACME server that proxies to an upstream CA via DNS-01.",
        lifespan=lifespan,
    )
    app.add_exception_handler(AcmeError, acme_error_handler)

    for module in (directory, accounts, orders, authz, certificates):
        app.include_router(module.router)
    app.include_router(management_api.router)
    app.include_router(hosts_api.router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the built Vue dashboard if present (see src/acme_lan/web). Mounted last so
    # it only catches paths not handled by the ACME / management routers.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="dashboard")

    return app


app = create_app()
