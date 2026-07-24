"""Background auto-renew scheduler.

Periodically finds managed hosts whose certificate is missing or expiring soon and runs
the issue-and-deploy flow for each. Enabled with ``ACME_LAN_AUTO_RENEW_ENABLED``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .config import get_settings
from .db import session_scope
from .hosts import Issuer, hosts_needing_renewal, renew_and_deploy

logger = logging.getLogger("acme_lan.scheduler")


async def renew_due_hosts(*, issuer: Issuer | None = None) -> list[dict[str, Any]]:
    """Renew and deploy every host currently due. Returns a per-host summary."""
    settings = get_settings()
    results: list[dict[str, Any]] = []
    async with session_scope() as session:
        due = await hosts_needing_renewal(session, settings.renew_before_days)
        for host in due:
            try:
                _cert, result = await renew_and_deploy(host, session, issuer=issuer)
                results.append({"host": host.name, "ok": result.ok, "detail": result.detail})
                logger.info("Renewed host %s: ok=%s %s", host.name, result.ok, result.detail)
            except Exception as exc:  # noqa: BLE001 - one host failing must not stop the rest
                results.append({"host": host.name, "ok": False, "detail": str(exc)})
                logger.warning("Renewal failed for host %s", host.name, exc_info=True)
    return results


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """Loop until ``stop_event`` is set, renewing due hosts each interval."""
    settings = get_settings()
    interval = settings.renew_check_interval_seconds
    logger.info("Auto-renew scheduler started (every %ss)", interval)
    while not stop_event.is_set():
        try:
            await renew_due_hosts()
        except Exception:  # noqa: BLE001
            logger.exception("Auto-renew tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            pass
    logger.info("Auto-renew scheduler stopped")
