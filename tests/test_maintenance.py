"""Tests for nonce/order garbage collection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from acme_lan.db import session_scope
from acme_lan.maintenance import purge_expired_nonces, purge_expired_orders
from acme_lan.models import Nonce, Order, OrderStatus


async def test_purge_expired_nonces(fresh_db):
    async with session_scope() as session:
        session.add(Nonce(value="old", created_at=datetime.now(UTC) - timedelta(hours=2)))
        session.add(Nonce(value="fresh", created_at=datetime.now(UTC)))
        await session.commit()

        removed = await purge_expired_nonces(session, max_age_seconds=3600)
        assert removed == 1
        remaining = {n.value for n in (await session.execute(_select_nonces())).scalars()}
        assert remaining == {"fresh"}


def _select_nonces():
    from sqlalchemy import select

    return select(Nonce)


async def test_purge_expired_orders_keeps_valid(fresh_db):
    past = datetime.now(UTC) - timedelta(days=1)
    async with session_scope() as session:
        session.add(
            Order(account_id="a", identifiers=[{"type": "dns", "value": "x"}],
                  status=OrderStatus.PENDING, expires_at=past)
        )
        session.add(
            Order(account_id="a", identifiers=[{"type": "dns", "value": "y"}],
                  status=OrderStatus.VALID, expires_at=past)
        )
        await session.commit()

        removed = await purge_expired_orders(session)
        assert removed == 1  # only the expired pending order is purged
        from sqlalchemy import select

        statuses = {o.status for o in (await session.execute(select(Order))).scalars()}
        assert statuses == {OrderStatus.VALID}
