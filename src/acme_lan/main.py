"""FastAPI application factory for the acme-lan server."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .acme import accounts, authz, certificates, directory, orders
from .acme.errors import AcmeError, acme_error_handler
from .db import init_db
from .management import api as management_api

FRONTEND_DIST = Path(__file__).resolve().parent / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


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

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Serve the built Vue dashboard if present (see src/acme_lan/web). Mounted last so
    # it only catches paths not handled by the ACME / management routers.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="dashboard")

    return app


app = create_app()
