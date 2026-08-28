"""Local user accounts, password hashing and server-side sessions.

Passwords are hashed with PBKDF2-HMAC-SHA256 from ``cryptography`` — already a dependency,
so no password library is pulled in for this. Sessions are rows rather than signed cookies
so that revoking one (logout, disabling a user) takes effect immediately.
"""

from __future__ import annotations

import base64
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User, UserSession, utcnow

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 480_000
SESSION_COOKIE = "acme_lan_session"


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    derived = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
    ).derive(password.encode())
    salt_b64 = base64.b64encode(salt).decode()
    hash_b64 = base64.b64encode(derived).decode()
    return f"{ALGORITHM}${iterations}${salt_b64}${hash_b64}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time password check; False for unusable/absent hashes."""
    if not password or not stored:
        return False
    try:
        algorithm, iterations, salt_b64, hash_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        derived = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=len(expected),
            salt=salt,
            iterations=int(iterations),
        ).derive(password.encode())
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived, expected)


async def count_users(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(User))).scalar() or 0)


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User).where(func.lower(User.username) == username.strip().lower())
    )
    return result.scalars().first()


async def get_user_by_oidc(session: AsyncSession, subject: str, email: str) -> User | None:
    result = await session.execute(select(User).where(User.oidc_subject == subject))
    user = result.scalars().first()
    if user is not None:
        return user
    if email:
        # First OIDC login for someone who already has a local account: adopt it rather
        # than creating a duplicate.
        result = await session.execute(
            select(User).where(func.lower(User.email) == email.strip().lower())
        )
        return result.scalars().first()
    return None


async def create_user(
    session: AsyncSession,
    *,
    username: str,
    password: str | None = None,
    email: str = "",
    provider: str = "local",
    oidc_subject: str | None = None,
    is_admin: bool = True,
) -> User:
    user = User(
        username=username.strip(),
        email=email.strip(),
        password_hash=hash_password(password) if password else "",
        provider=provider,
        oidc_subject=oidc_subject,
        is_admin=is_admin,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    user = await get_user_by_username(session, username)
    if user is None or user.disabled or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def start_session(
    session: AsyncSession, user: User, *, lifetime_hours: int = 12
) -> UserSession:
    await purge_expired_sessions(session)
    row = UserSession(
        token=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=max(1, lifetime_hours)),
    )
    user.last_login_at = utcnow()
    session.add_all([row, user])
    await session.commit()
    await session.refresh(row)
    return row


async def resolve_session(session: AsyncSession, token: str | None) -> User | None:
    """Return the live user for a session token, or None if absent/expired/disabled."""
    if not token:
        return None
    row = await session.get(UserSession, token)
    if row is None:
        return None
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires <= datetime.now(UTC):
        await session.delete(row)
        await session.commit()
        return None
    user = await session.get(User, row.user_id)
    if user is None or user.disabled:
        return None
    return user


async def end_session(session: AsyncSession, token: str | None) -> None:
    if not token:
        return
    row = await session.get(UserSession, token)
    if row is not None:
        await session.delete(row)
        await session.commit()


async def end_sessions_for_user(session: AsyncSession, user_id: str) -> None:
    await session.execute(delete(UserSession).where(UserSession.user_id == user_id))
    await session.commit()


async def purge_expired_sessions(session: AsyncSession) -> None:
    await session.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
