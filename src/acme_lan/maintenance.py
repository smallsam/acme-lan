"""Housekeeping: purge stale nonces and expired orders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Nonce, Order, OrderStatus


async def purge_expired_nonces(session: AsyncSession, max_age_seconds: int) -> int:
    """Delete unused nonces older than ``max_age_seconds``. Returns rows removed."""
    cutoff = datetime.now(UTC) - timedelta(seconds=max_age_seconds)
    result = await session.execute(delete(Nonce).where(Nonce.created_at < cutoff))
    await session.commit()
    return result.rowcount or 0


async def purge_expired_orders(session: AsyncSession) -> int:
    """Delete pending/invalid orders past their expiry. Valid orders are kept."""
    now = datetime.now(UTC)
    orders = (await session.execute(select(Order))).scalars().all()
    removed = 0
    for order in orders:
        if order.status in (OrderStatus.VALID, OrderStatus.PROCESSING):
            continue
        expires = order.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires is not None and expires < now:
            await session.delete(order)
            removed += 1
    if removed:
        await session.commit()
    return removed
