"""SQLite-backed user + session-token store."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from ..config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    REAL NOT NULL,
    profile_dir   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token       TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user    ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
"""


# ── Data model ────────────────────────────────────────────────────────────────


@dataclass
class User:
    user_id: str
    username: str
    role: str          # "admin" | "user"
    created_at: float
    profile_dir: str   # per-user Playwright browser-profile path

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "profile_dir": self.profile_dir,
        }


def _row_to_user(row: aiosqlite.Row) -> User:
    return User(
        user_id=row["user_id"],
        username=row["username"],
        role=row["role"],
        created_at=row["created_at"],
        profile_dir=row["profile_dir"],
    )


# ── Store ─────────────────────────────────────────────────────────────────────


class UserStore:
    """Persistent user + session store backed by a single SQLite file."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def _ensure(self) -> aiosqlite.Connection:
        if self._db is None:
            path = self._db_path or (settings.output_path / "auth.db")
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(str(path))
            self._db.row_factory = aiosqlite.Row
            await self._db.executescript(_SCHEMA)
            await self._db.commit()
        return self._db

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Users ─────────────────────────────────────────────────────────────────

    async def create_user(
        self, username: str, password_hash: str, role: str = "user"
    ) -> User:
        db = await self._ensure()
        user_id = uuid.uuid4().hex[:16]
        created_at = time.time()
        profile_dir = str(settings.output_path / "profiles" / username)
        await db.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, password_hash, role, created_at, profile_dir),
        )
        await db.commit()
        return User(user_id, username, role, created_at, profile_dir)

    async def get_user_by_username(self, username: str) -> tuple[User, str] | None:
        """Return (User, password_hash) or None."""
        db = await self._ensure()
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        return _row_to_user(row), row["password_hash"]

    async def get_user_by_id(self, user_id: str) -> User | None:
        db = await self._ensure()
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_user(row) if row else None

    async def list_users(self) -> list[User]:
        db = await self._ensure()
        async with db.execute("SELECT * FROM users ORDER BY created_at") as cur:
            rows = await cur.fetchall()
        return [_row_to_user(r) for r in rows]

    async def delete_user(self, user_id: str) -> bool:
        """Delete user and cascade-delete their sessions. Returns True if found."""
        db = await self._ensure()
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        async with db.execute(
            "DELETE FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            affected = cur.rowcount
        await db.commit()
        return affected > 0

    # ── Sessions ──────────────────────────────────────────────────────────────

    async def create_session(self, user_id: str, token: str, ttl: int) -> float:
        """Store token, return expires_at timestamp."""
        expires_at = time.time() + ttl
        db = await self._ensure()
        await db.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?)",
            (token, user_id, time.time(), expires_at),
        )
        await db.commit()
        return expires_at

    async def get_session_user_id(self, token: str) -> str | None:
        """Return user_id for a valid non-expired token, else None."""
        db = await self._ensure()
        async with db.execute(
            "SELECT user_id, expires_at FROM sessions WHERE token = ?", (token,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        if row["expires_at"] < time.time():
            await self.revoke_session(token)
            return None
        return row["user_id"]

    async def revoke_session(self, token: str) -> None:
        db = await self._ensure()
        await db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        await db.commit()

    async def revoke_all_sessions(self, user_id: str) -> None:
        db = await self._ensure()
        await db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        await db.commit()

    async def purge_expired_sessions(self) -> int:
        """Delete all expired sessions. Returns number of rows removed."""
        db = await self._ensure()
        async with db.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (time.time(),)
        ) as cur:
            count = cur.rowcount
        await db.commit()
        return count


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: UserStore | None = None


async def get_user_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore()
        await _store._ensure()
    return _store
