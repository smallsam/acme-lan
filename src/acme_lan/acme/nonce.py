"""Anti-replay nonce issuance and single-use consumption (RFC 8555 §6.5)."""

from __future__ import annotations

import secrets

from sqlalchemy import delete, select

from ..db import session_scope
from ..models import Nonce
from .errors import bad_nonce


async def issue_nonce() -> str:
    """Create, persist and return a fresh nonce."""
    value = secrets.token_urlsafe(24)
    async with session_scope() as session:
        session.add(Nonce(value=value))
        await session.commit()
    return value


async def consume_nonce(value: str) -> None:
    """Consume a nonce, raising :func:`bad_nonce` if unknown or already used.

    Deletion is the atomic check: if no row was removed the nonce was never issued
    or has already been spent, so the request is a replay.
    """
    async with session_scope() as session:
        result = await session.execute(delete(Nonce).where(Nonce.value == value))
        await session.commit()
        if result.rowcount == 0:
            raise bad_nonce()


async def nonce_exists(value: str) -> bool:
    async with session_scope() as session:
        row = await session.execute(select(Nonce).where(Nonce.value == value))
        return row.first() is not None
