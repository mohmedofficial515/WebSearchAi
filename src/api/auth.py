"""Auth: PBKDF2 passwords, server-side Bearer tokens, FastAPI dependencies + router."""

from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..config import settings
from ..storage.users import User, UserStore, get_user_store
from ..utils.logger import log

# ── Crypto config ─────────────────────────────────────────────────────────────

TOKEN_TTL_SECONDS: int = 86_400 * 7   # 7 days
_PBKDF2_ITERS: int = 260_000
_PBKDF2_HASH: str = "sha256"
_TOKEN_BYTES: int = 32


# ── Crypto helpers ────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Return a salted PBKDF2-SHA256 hash suitable for storage."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH, password.encode(), salt.encode(), _PBKDF2_ITERS
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """True when *password* matches the stored PBKDF2 hash."""
    try:
        salt, expected = stored_hash.split("$", 1)
        dk = hashlib.pbkdf2_hmac(
            _PBKDF2_HASH, password.encode(), salt.encode(), _PBKDF2_ITERS
        )
        return secrets.compare_digest(dk.hex(), expected)
    except Exception:  # noqa: BLE001
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


# ── FastAPI dependencies ──────────────────────────────────────────────────────


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    store: UserStore = Depends(get_user_store),
) -> User:
    """Dependency: validates Bearer token and returns the authenticated User.

    Raises HTTP 501 when AUTH_ENABLED=false (auth not configured yet).
    Raises HTTP 401 on missing/invalid/expired tokens.
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="AUTH_ENABLED=false — set it to true in .env to enable auth",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    user_id = await store.get_session_user_id(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalid or expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency: same as get_current_user but also asserts role='admin'."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return current_user


# ── Pydantic request models ───────────────────────────────────────────────────


class AuthRegisterBody(BaseModel):
    username: str
    password: str
    role: str = "user"


class AuthLoginBody(BaseModel):
    username: str
    password: str


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_guard() -> None:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Set AUTH_ENABLED=true in .env to enable auth",
        )


@router.post("/register", status_code=201)
async def auth_register(
    body: AuthRegisterBody,
    store: UserStore = Depends(get_user_store),
) -> dict:
    """Create a new user account. The very first registered user becomes admin."""
    _auth_guard()
    if len(body.username) < 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username must be ≥ 3 chars")
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "password must be ≥ 8 chars")

    existing = await store.list_users()
    role = "admin" if not existing else body.role

    try:
        user = await store.create_user(body.username, hash_password(body.password), role)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Username already taken: {body.username}"
        ) from exc

    log.info("User registered: %s (%s)", user.username, user.role)
    return {"user_id": user.user_id, "username": user.username, "role": user.role}


@router.post("/login")
async def auth_login(
    body: AuthLoginBody,
    store: UserStore = Depends(get_user_store),
) -> dict:
    """Log in and receive a Bearer token."""
    _auth_guard()
    row = await store.get_user_by_username(body.username)
    if not row or not verify_password(body.password, row[1]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    user, _ = row
    token = generate_token()
    expires_at = await store.create_session(user.user_id, token, TOKEN_TTL_SECONDS)
    log.info("User logged in: %s", user.username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at,
        "user": user.to_dict(),
    }


@router.post("/logout")
async def auth_logout(
    authorization: Annotated[str | None, Header()] = None,
    store: UserStore = Depends(get_user_store),
) -> dict:
    """Revoke the current session token (safe to call even when auth is off)."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        await store.revoke_session(token)
    return {"ok": True}


@router.get("/me")
async def auth_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Return the currently authenticated user's profile."""
    return current_user.to_dict()


@router.get("/users")
async def auth_list_users(
    _admin: Annotated[User, Depends(require_admin)],
    store: UserStore = Depends(get_user_store),
) -> list[dict]:
    """[Admin] List all registered users."""
    return [u.to_dict() for u in await store.list_users()]


@router.delete("/users/{user_id}")
async def auth_delete_user(
    user_id: str,
    current_user: Annotated[User, Depends(require_admin)],
    store: UserStore = Depends(get_user_store),
) -> dict:
    """[Admin] Delete a user and revoke all their sessions."""
    if user_id == current_user.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete your own account")
    ok = await store.delete_user(user_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return {"ok": True, "deleted": user_id}
