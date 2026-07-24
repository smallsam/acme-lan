"""FastAPI application factory for the acme-lan server."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .acme import accounts, authz, certificates, directory, orders
from .acme.errors import AcmeError, acme_error_handler
from .db import init_db


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

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
