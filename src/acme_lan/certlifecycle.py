"""Certificate lifecycle helpers: expiry status, retirement, and expiry queries.

Every issued certificate is a row in the ``certificate`` table (renewals are new rows,
grouped by host/domains), so renewal history is inherently tracked. A certificate can be
*retired* ("no longer required") so it stops raising expiry warnings and auto-renewal.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Certificate, utcnow


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def expiry_info(cert: Certificate, warn_days: int) -> dict[str, Any]:
    """Return expiry status for a certificate."""
    not_after = _aware(cert.not_after)
    if not_after is None:
        return {"days_until_expiry": None, "expired": None, "expiring_soon": False}
    days = (not_after - datetime.now(UTC)).days
    expired = days < 0
    return {
        "days_until_expiry": days,
        "expired": expired,
        "expiring_soon": (not cert.retired) and days <= warn_days,
    }


async def expiring_certificates(
    session: AsyncSession, warn_days: int
) -> list[Certificate]:
    """Non-retired certificates that are expiring within ``warn_days`` (or already expired).

    Only the newest certificate per (host/domains) group is considered, so a superseded
    older cert doesn't keep firing warnings after a successful renewal.
    """
    certs = (
        await session.execute(select(Certificate).where(Certificate.retired == False))  # noqa: E712
    ).scalars().all()

    # Keep the latest cert per group key (host_id or sorted domains).
    latest: dict[str, Certificate] = {}
    for cert in certs:
        key = cert.host_id or ",".join(sorted(cert.domains or [])) or cert.id
        current = latest.get(key)
        if current is None or _issued(cert) > _issued(current):
            latest[key] = cert

    now = datetime.now(UTC)
    result = []
    for cert in latest.values():
        not_after = _aware(cert.not_after)
        if not_after is None:
            continue
        if (not_after - now).days <= warn_days:
            result.append(cert)
    return result


def _issued(cert: Certificate) -> datetime:
    return _aware(cert.issued_at) or datetime.min.replace(tzinfo=UTC)


async def retire_certificate(
    session: AsyncSession, cert: Certificate, reason: str | None = None
) -> Certificate:
    cert.retired = True
    cert.retired_at = utcnow()
    cert.retired_reason = reason
    session.add(cert)
    await session.commit()
    await session.refresh(cert)
    return cert


async def unretire_certificate(session: AsyncSession, cert: Certificate) -> Certificate:
    cert.retired = False
    cert.retired_at = None
    cert.retired_reason = None
    session.add(cert)
    await session.commit()
    await session.refresh(cert)
    return cert
