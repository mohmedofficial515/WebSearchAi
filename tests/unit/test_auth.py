"""Unit tests for Phase 8 — Auth & Multi-User."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ── Crypto helpers ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_hash_password_produces_salted_hash():
    from src.api.auth import hash_password

    h = hash_password("secret123")
    assert "$" in h
    salt, dk = h.split("$", 1)
    assert len(salt) == 32   # 16 bytes → 32 hex chars
    assert len(dk) == 64     # SHA-256 → 32 bytes → 64 hex chars


@pytest.mark.unit
def test_hash_password_two_calls_differ():
    from src.api.auth import hash_password

    assert hash_password("same_pass") != hash_password("same_pass")


@pytest.mark.unit
def test_verify_password_correct():
    from src.api.auth import hash_password, verify_password

    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


@pytest.mark.unit
def test_verify_password_wrong():
    from src.api.auth import hash_password, verify_password

    h = hash_password("correct")
    assert verify_password("wrong", h) is False


@pytest.mark.unit
def test_verify_password_malformed_hash_returns_false():
    from src.api.auth import verify_password

    assert verify_password("anything", "not_a_valid_hash") is False
    assert verify_password("anything", "") is False


@pytest.mark.unit
def test_generate_token_is_long_enough():
    from src.api.auth import generate_token

    token = generate_token()
    assert len(token) >= 40   # 32 bytes base64url → ≥43 chars


@pytest.mark.unit
def test_generate_token_is_unique():
    from src.api.auth import generate_token

    assert generate_token() != generate_token()


# ── User dataclass ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_user_to_dict():
    from src.storage.users import User

    u = User("uid1", "alice", "admin", 1000.0, "/profiles/alice")
    d = u.to_dict()
    assert d["user_id"] == "uid1"
    assert d["username"] == "alice"
    assert d["role"] == "admin"
    assert d["profile_dir"] == "/profiles/alice"
    assert d["created_at"] == 1000.0


# ── UserStore (async, isolated tmp SQLite) ────────────────────────────────────


@pytest.fixture
async def store(tmp_path: Path):
    from src.storage.users import UserStore

    s = UserStore(db_path=tmp_path / "auth_test.db")
    await s._ensure()
    yield s
    await s.close()


@pytest.mark.unit
async def test_create_and_get_user_by_username(store):
    user = await store.create_user("bob", "hash_abc", "user")
    assert user.username == "bob"
    assert user.role == "user"
    assert len(user.user_id) == 16

    row = await store.get_user_by_username("bob")
    assert row is not None
    fetched, pw_hash = row
    assert fetched.username == "bob"
    assert pw_hash == "hash_abc"


@pytest.mark.unit
async def test_get_user_by_id(store):
    created = await store.create_user("carol", "hash_x", "admin")
    found = await store.get_user_by_id(created.user_id)
    assert found is not None
    assert found.username == "carol"
    assert found.role == "admin"


@pytest.mark.unit
async def test_get_user_by_id_not_found(store):
    assert await store.get_user_by_id("no_such_id") is None


@pytest.mark.unit
async def test_get_user_by_username_not_found(store):
    assert await store.get_user_by_username("ghost") is None


@pytest.mark.unit
async def test_list_users_empty(store):
    assert await store.list_users() == []


@pytest.mark.unit
async def test_list_users_multiple(store):
    await store.create_user("u1", "h1")
    await store.create_user("u2", "h2")
    users = await store.list_users()
    assert len(users) == 2
    assert {u.username for u in users} == {"u1", "u2"}


@pytest.mark.unit
async def test_delete_user_returns_true(store):
    user = await store.create_user("dave", "hash_d")
    ok = await store.delete_user(user.user_id)
    assert ok is True
    assert await store.get_user_by_username("dave") is None


@pytest.mark.unit
async def test_delete_nonexistent_user_returns_false(store):
    assert await store.delete_user("ghost_id") is False


# ── Session management ────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_create_and_validate_session(store):
    user = await store.create_user("eve", "hash_e")
    await store.create_session(user.user_id, "tok_valid", ttl=3600)
    uid = await store.get_session_user_id("tok_valid")
    assert uid == user.user_id


@pytest.mark.unit
async def test_expired_session_returns_none(store):
    user = await store.create_user("frank", "hash_f")
    await store.create_session(user.user_id, "tok_old", ttl=-1)  # already expired
    assert await store.get_session_user_id("tok_old") is None


@pytest.mark.unit
async def test_unknown_token_returns_none(store):
    assert await store.get_session_user_id("nonexistent") is None


@pytest.mark.unit
async def test_revoke_session(store):
    user = await store.create_user("grace", "hash_g")
    await store.create_session(user.user_id, "tok_revoke", ttl=3600)
    await store.revoke_session("tok_revoke")
    assert await store.get_session_user_id("tok_revoke") is None


@pytest.mark.unit
async def test_revoke_all_sessions(store):
    user = await store.create_user("hank", "hash_h")
    for i in range(3):
        await store.create_session(user.user_id, f"tok_{i}", ttl=3600)
    await store.revoke_all_sessions(user.user_id)
    for i in range(3):
        assert await store.get_session_user_id(f"tok_{i}") is None


@pytest.mark.unit
async def test_delete_user_cascades_sessions(store):
    user = await store.create_user("ivan", "hash_i")
    await store.create_session(user.user_id, "tok_ivan", ttl=3600)
    await store.delete_user(user.user_id)
    assert await store.get_session_user_id("tok_ivan") is None


@pytest.mark.unit
async def test_purge_expired_sessions_count(store):
    user = await store.create_user("judy", "hash_j")
    await store.create_session(user.user_id, "exp1", ttl=-10)
    await store.create_session(user.user_id, "exp2", ttl=-20)
    await store.create_session(user.user_id, "valid", ttl=3600)
    deleted = await store.purge_expired_sessions()
    assert deleted == 2
    assert await store.get_session_user_id("valid") == user.user_id


# ── Pydantic models ───────────────────────────────────────────────────────────


@pytest.mark.unit
def test_auth_register_body_default_role_is_user():
    from src.api.auth import AuthRegisterBody

    body = AuthRegisterBody(username="alice", password="pass1234")
    assert body.role == "user"


@pytest.mark.unit
def test_auth_login_body_fields():
    from src.api.auth import AuthLoginBody

    body = AuthLoginBody(username="alice", password="pass1234")
    assert body.username == "alice"
    assert body.password == "pass1234"


# ── API route registration ────────────────────────────────────────────────────


@pytest.mark.unit
def test_auth_routes_registered_in_app():
    from src.api.main import app

    paths = {r.path for r in app.routes}
    assert "/api/auth/register" in paths
    assert "/api/auth/login" in paths
    assert "/api/auth/logout" in paths
    assert "/api/auth/me" in paths
    assert "/api/auth/users" in paths
    assert "/api/auth/users/{user_id}" in paths


# ── get_current_user dependency ───────────────────────────────────────────────


@pytest.mark.unit
async def test_get_current_user_no_header_raises_401():
    from fastapi import HTTPException
    from src.api.auth import get_current_user

    mock_store = AsyncMock()
    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization=None, store=mock_store)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_get_current_user_wrong_scheme_raises_401():
    from fastapi import HTTPException
    from src.api.auth import get_current_user

    mock_store = AsyncMock()
    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization="Basic dXNlcjpwYXNz", store=mock_store)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_get_current_user_expired_token_raises_401():
    from fastapi import HTTPException
    from src.api.auth import get_current_user

    mock_store = AsyncMock()
    mock_store.get_session_user_id = AsyncMock(return_value=None)
    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization="Bearer bad_token", store=mock_store)
    assert exc.value.status_code == 401


@pytest.mark.unit
async def test_get_current_user_auth_disabled_raises_501():
    from fastapi import HTTPException
    from src.api.auth import get_current_user

    mock_store = AsyncMock()
    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = False
        with pytest.raises(HTTPException) as exc:
            await get_current_user(authorization="Bearer sometoken", store=mock_store)
    assert exc.value.status_code == 501


@pytest.mark.unit
async def test_get_current_user_valid_token_returns_user(store):
    from src.api.auth import get_current_user

    user = await store.create_user("ken", "hash_k")
    token = "valid_ken_token"
    await store.create_session(user.user_id, token, ttl=3600)

    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        result = await get_current_user(
            authorization=f"Bearer {token}", store=store
        )
    assert result.username == "ken"


# ── require_admin dependency ──────────────────────────────────────────────────


@pytest.mark.unit
async def test_require_admin_grants_admin_user(store):
    from src.api.auth import require_admin

    user = await store.create_user("laura", "hash_l", role="admin")
    token = "admin_tok"
    await store.create_session(user.user_id, token, ttl=3600)

    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        result = await require_admin(
            current_user=await _get_user(token, store)
        )
    assert result.role == "admin"


@pytest.mark.unit
async def test_require_admin_rejects_non_admin(store):
    from fastapi import HTTPException
    from src.api.auth import require_admin
    from src.storage.users import User

    non_admin = User("x", "mike", "user", time.time(), "/p/mike")
    with pytest.raises(HTTPException) as exc:
        await require_admin(current_user=non_admin)
    assert exc.value.status_code == 403


# ── Config setting ────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_auth_enabled_default_is_false():
    from src.config import settings

    assert settings.auth_enabled is False


# ── helper used by admin tests above ─────────────────────────────────────────


async def _get_user(token: str, store):
    from src.api.auth import get_current_user

    with patch("src.api.auth.settings") as ms:
        ms.auth_enabled = True
        return await get_current_user(authorization=f"Bearer {token}", store=store)
