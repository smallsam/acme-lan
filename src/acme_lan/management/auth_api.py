"""Login, logout, user administration and the OIDC round trip."""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import get_session
from ..models import OidcState, User
from ..oidc import (
    OidcError,
    authorize_url,
    claim_identity,
    decode_jwt_claims,
    exchange_code,
    fetch_discovery,
    make_pkce,
    validate_claims,
)
from ..users import (
    SESSION_COOKIE,
    authenticate,
    count_users,
    create_user,
    end_session,
    end_sessions_for_user,
    get_user_by_oidc,
    get_user_by_username,
    hash_password,
    start_session,
    verify_password,
)
from .auth import require_admin, require_user

router = APIRouter(prefix="/api", tags=["auth"])

OIDC_CALLBACK_PATH = "/api/auth/oidc/callback"


def _user_view(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "provider": user.provider,
        "is_admin": user.is_admin,
        "disabled": user.disabled,
        "has_password": bool(user.password_hash),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _redirect_uri() -> str:
    """Absolute callback URL, derived from external_url so it matches what the IdP sees."""
    base = get_settings().external_url.rstrip("/")
    return f"{base}{OIDC_CALLBACK_PATH}"


def _set_session_cookie(response: Response, token: str, *, lifetime_hours: int) -> None:
    secure = urlparse(get_settings().external_url).scheme == "https"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=lifetime_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


@router.get("/auth/status")
async def auth_status(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Public: what login methods exist, and who (if anyone) is signed in."""
    from ..users import resolve_session

    settings = get_settings()
    user = await resolve_session(session, session_cookie)
    users = await count_users(session)
    return {
        "auth_required": settings.auth_required,
        "local_login_enabled": users > 0,
        "oidc_enabled": settings.oidc_configured,
        "oidc_provider": settings.oidc_provider,
        "token_auth_enabled": bool(settings.admin_token),
        # No accounts yet: the UI offers to create the first one.
        "needs_setup": users == 0,
        "oidc_redirect_uri": _redirect_uri(),
        "user": _user_view(user) if user else None,
    }


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(
    body: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    settings = get_settings()
    user = await authenticate(session, body.username, body.password)
    if user is None:
        raise HTTPException(401, "Incorrect username or password")
    row = await start_session(session, user, lifetime_hours=settings.session_lifetime_hours)
    _set_session_cookie(response, row.token, lifetime_hours=settings.session_lifetime_hours)
    return {"user": _user_view(user)}


@router.post("/auth/logout")
async def logout(
    response: Response,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    await end_session(session, session_cookie)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "signed out"}


class SetupRequest(BaseModel):
    username: str
    password: str = Field(min_length=8)
    email: str = ""


@router.post("/auth/setup", status_code=201)
async def first_user(
    body: SetupRequest, response: Response, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Create the first administrator. Only available while no users exist."""
    if await count_users(session) > 0:
        raise HTTPException(409, "Users already exist; sign in and add users from Settings")
    user = await create_user(
        session, username=body.username, password=body.password, email=body.email
    )
    settings = get_settings()
    row = await start_session(session, user, lifetime_hours=settings.session_lifetime_hours)
    _set_session_cookie(response, row.token, lifetime_hours=settings.session_lifetime_hours)
    return {"user": _user_view(user)}


# --- user administration ---


@router.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_session), _: Any = Depends(require_admin)
) -> list[dict[str, Any]]:
    rows = (await session.execute(select(User).order_by(User.created_at))).scalars().all()
    return [_user_view(u) for u in rows]


class UserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    email: str = ""
    is_admin: bool = True


@router.post("/users", status_code=201)
async def add_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_session),
    _: Any = Depends(require_admin),
) -> dict[str, Any]:
    if await get_user_by_username(session, body.username):
        raise HTTPException(409, f"User {body.username!r} already exists")
    user = await create_user(
        session,
        username=body.username,
        password=body.password,
        email=body.email,
        is_admin=body.is_admin,
    )
    return _user_view(user)


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    email: str | None = None
    is_admin: bool | None = None
    disabled: bool | None = None


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    session: AsyncSession = Depends(get_session),
    _: Any = Depends(require_admin),
) -> dict[str, Any]:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        # A password change invalidates that user's other sessions.
        await end_sessions_for_user(session, user.id)
    if body.email is not None:
        user.email = body.email.strip()
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.disabled is not None:
        user.disabled = body.disabled
        if body.disabled:
            await end_sessions_for_user(session, user.id)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_view(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    _: Any = Depends(require_admin),
) -> None:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if await count_users(session) <= 1:
        raise HTTPException(409, "Refusing to delete the last user; you would be locked out")
    await end_sessions_for_user(session, user.id)
    await session.delete(user)
    await session.commit()


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


@router.post("/auth/password")
async def change_own_password(
    body: PasswordChange,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(403, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    session.add(user)
    await session.commit()
    return {"status": "password changed"}


# --- OIDC ---


@router.get("/auth/oidc/start")
async def oidc_start(
    next: str = "/", session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    settings = get_settings()
    if not settings.oidc_configured:
        raise HTTPException(400, "OIDC is not configured")
    try:
        document = await fetch_discovery(settings.oidc_discovery)
    except OidcError as exc:
        raise HTTPException(502, f"OIDC discovery failed: {exc}") from exc

    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    redirect_uri = _redirect_uri()
    session.add(
        OidcState(
            state=state,
            nonce=nonce,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            next_url=next if next.startswith("/") else "/",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
    )
    await session.commit()
    return RedirectResponse(
        authorize_url(
            document,
            client_id=settings.oidc_client_id,
            redirect_uri=redirect_uri,
            scopes=settings.oidc_scopes,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
        )
    )


@router.get("/auth/oidc/callback")
async def oidc_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    settings = get_settings()
    if error:
        return _oidc_failure(": ".join(filter(None, [error, error_description])))
    if not code or not state:
        return _oidc_failure("the provider did not return an authorization code")

    row = await session.get(OidcState, state)
    if row is None:
        return _oidc_failure("this login request is unknown or has already been used")
    # Copy what we need before deleting the row: the ORM object is unusable afterwards.
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    nonce, verifier = row.nonce, row.code_verifier
    callback_uri, next_url = row.redirect_uri, row.next_url or "/"
    # Single-use: drop the state row before doing anything else with the code.
    await session.delete(row)
    await session.commit()
    if expires <= datetime.now(UTC):
        return _oidc_failure("this login request expired; please try again")

    try:
        document = await fetch_discovery(settings.oidc_discovery)
        tokens = await exchange_code(
            document,
            code=code,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            redirect_uri=callback_uri,
            code_verifier=verifier,
        )
        claims = decode_jwt_claims(tokens["id_token"])
        validate_claims(
            claims,
            issuer=document.get("issuer", ""),
            client_id=settings.oidc_client_id,
            nonce=nonce,
            now=int(time.time()),
        )
    except OidcError as exc:
        return _oidc_failure(str(exc))

    subject, email, name = claim_identity(claims)
    if not subject:
        return _oidc_failure("the ID token carried no subject claim")

    allowed = [e.strip().lower() for e in settings.oidc_allowed_emails.split(",") if e.strip()]
    if allowed and email.lower() not in allowed:
        return _oidc_failure(f"{email or 'this account'} is not in the allowed list")

    user = await get_user_by_oidc(session, subject, email)
    if user is None:
        if not settings.oidc_auto_create_users:
            return _oidc_failure(
                f"no account exists for {email or subject} and automatic creation is off"
            )
        user = await create_user(
            session,
            username=email or name or subject,
            email=email,
            provider="oidc",
            oidc_subject=subject,
        )
    else:
        if user.disabled:
            return _oidc_failure("this account is disabled")
        # Bind the subject on first sign-in so later renames still resolve.
        if not user.oidc_subject:
            user.oidc_subject = subject
            if not user.email and email:
                user.email = email
            session.add(user)
            await session.commit()

    row_session = await start_session(
        session, user, lifetime_hours=settings.session_lifetime_hours
    )
    response = RedirectResponse(next_url)
    _set_session_cookie(
        response, row_session.token, lifetime_hours=settings.session_lifetime_hours
    )
    return response


def _oidc_failure(message: str) -> RedirectResponse:
    """Send the browser back to the dashboard with the reason, rather than a bare 500."""
    from urllib.parse import quote

    return RedirectResponse(f"/?login_error={quote(message[:300])}")


@router.get("/auth/oidc/preview")
async def oidc_preview(_: Any = Depends(require_admin)) -> dict[str, Any]:
    """Check the OIDC settings by resolving discovery — used by the Test button."""
    settings = get_settings()
    result: dict[str, Any] = {
        "provider": settings.oidc_provider,
        "discovery_url": settings.oidc_discovery,
        "redirect_uri": _redirect_uri(),
        "client_id_set": bool(settings.oidc_client_id),
        "client_secret_set": bool(settings.oidc_client_secret),
    }
    if not settings.oidc_discovery:
        result["ok"] = False
        result["detail"] = (
            "Set the Entra directory (tenant) ID, or a discovery URL for a generic provider."
        )
        return result
    try:
        document = await fetch_discovery(settings.oidc_discovery)
    except OidcError as exc:
        result["ok"] = False
        result["detail"] = str(exc)
        return result
    result["ok"] = True
    result["issuer"] = document.get("issuer")
    result["authorization_endpoint"] = document.get("authorization_endpoint")
    result["detail"] = "Discovery succeeded."
    return result
