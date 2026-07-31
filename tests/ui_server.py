"""Seed a temporary database and serve acme-lan for Playwright UI tests.

Playwright's ``webServer`` launches this (see src/acme_lan/web/playwright.config.ts). It
creates a throwaway SQLite database with one certificate and one managed host so the
dashboard has something to render, then serves the built dashboard + API on
``ACME_LAN_UI_PORT`` (default 8123). No upstream CA or admin token is involved.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import timedelta

from cryptography.fernet import Fernet

PORT = int(os.environ.get("ACME_LAN_UI_PORT", "8123"))
DB_PATH = os.path.join(tempfile.gettempdir(), "acme_lan_ui.db")

# A clean, self-contained environment for the UI under test.
for stale in (DB_PATH, DB_PATH + "-journal"):
    if os.path.exists(stale):
        os.remove(stale)
os.environ["ACME_LAN_DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["ACME_LAN_EXTERNAL_URL"] = f"http://127.0.0.1:{PORT}"
os.environ["ACME_LAN_SECRET_KEY"] = os.environ.get(
    "ACME_LAN_SECRET_KEY", Fernet.generate_key().decode()
)
os.environ.pop("ACME_LAN_ADMIN_TOKEN", None)  # open API so the UI works without a token

from acme_lan import config  # noqa: E402

config.reset_settings_cache()


async def _seed() -> None:
    from acme_lan.db import init_db, reset_engine, session_scope
    from acme_lan.models import Certificate, ManagedHost, utcnow

    await init_db()
    async with session_scope() as session:
        session.add(
            Certificate(
                domains=["db.lan.test"],
                subject="CN=db.lan.test",
                serial="ab12cd",
                not_after=utcnow() + timedelta(days=10),  # expiring soon -> amber badge
            )
        )
        host = ManagedHost(
            name="printer01",
            domains=["printer01.lan.test"],
            address="192.168.3.9",
            deploy_plugin="local",
            csr_source="device",
        )
        session.add(host)
        await session.flush()
        # A cert pushed to the managed host, so the cert<->device link renders both ways.
        session.add(
            Certificate(
                host_id=host.id,
                domains=["printer01.lan.test"],
                subject="CN=printer01.lan.test",
                serial="ef34gh",
                not_after=utcnow() + timedelta(days=60),
            )
        )
        await session.commit()
    # Dispose so uvicorn's event loop gets a fresh engine.
    await reset_engine()


def main() -> None:
    asyncio.run(_seed())
    import uvicorn

    uvicorn.run("acme_lan.main:app", host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
