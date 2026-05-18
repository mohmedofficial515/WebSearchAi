"""SQLite-backed long-term agent memory store."""
from __future__ import annotations
import json, time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    url TEXT PRIMARY KEY,
    last_visited_at REAL,
    visit_count INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_url TEXT NOT NULL,
    flow_type TEXT NOT NULL,
    flow_data TEXT NOT NULL,
    selectors TEXT,
    success_count INTEGER DEFAULT 1,
    last_used_at REAL,
    FOREIGN KEY(site_url) REFERENCES sites(url) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS login_profiles (
    site_url TEXT PRIMARY KEY,
    profile_path TEXT NOT NULL,
    email TEXT,
    last_used_at REAL
);
CREATE TABLE IF NOT EXISTS memory_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_url TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    metadata TEXT,
    created_at REAL
);
"""

@dataclass
class FlowRecord:
    site_url: str
    flow_type: str
    flow_data: dict
    selectors: dict | None = None
    success_count: int = 1

class MemoryStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def _ensure(self) -> aiosqlite.Connection:
        if self._db is None:
            await self.init()
        return self._db  # type: ignore

    # ── sites ────────────────────────────────────────────────────────────────

    async def touch_site(self, url: str) -> None:
        db = await self._ensure()
        now = time.time()
        await db.execute(
            """INSERT INTO sites(url, last_visited_at, visit_count)
               VALUES(?,?,1)
               ON CONFLICT(url) DO UPDATE SET
                   last_visited_at=excluded.last_visited_at,
                   visit_count=visit_count+1""",
            (url, now),
        )
        await db.commit()

    async def list_sites(self) -> list[dict]:
        db = await self._ensure()
        async with db.execute(
            "SELECT url, last_visited_at, visit_count FROM sites ORDER BY last_visited_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def forget_site(self, url: str) -> None:
        db = await self._ensure()
        await db.execute("DELETE FROM sites WHERE url=?", (url,))
        await db.execute("DELETE FROM flows WHERE site_url=?", (url,))
        await db.execute("DELETE FROM login_profiles WHERE site_url=?", (url,))
        await db.execute("DELETE FROM memory_vectors WHERE site_url=?", (url,))
        await db.commit()

    # ── flows ────────────────────────────────────────────────────────────────

    async def remember_flow(
        self, site: str, flow_type: str, flow: dict, selectors: dict | None = None
    ) -> None:
        db = await self._ensure()
        await self.touch_site(site)
        existing = await self._get_flow(site, flow_type)
        now = time.time()
        if existing:
            await db.execute(
                """UPDATE flows SET flow_data=?, selectors=?, success_count=success_count+1,
                   last_used_at=? WHERE site_url=? AND flow_type=?""",
                (json.dumps(flow), json.dumps(selectors) if selectors else None, now, site, flow_type),
            )
        else:
            await db.execute(
                """INSERT INTO flows(site_url, flow_type, flow_data, selectors, last_used_at)
                   VALUES(?,?,?,?,?)""",
                (site, flow_type, json.dumps(flow), json.dumps(selectors) if selectors else None, now),
            )
        await db.commit()

    async def _get_flow(self, site: str, flow_type: str) -> dict | None:
        db = await self._ensure()
        async with db.execute(
            "SELECT * FROM flows WHERE site_url=? AND flow_type=? ORDER BY last_used_at DESC LIMIT 1",
            (site, flow_type),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        r = dict(row)
        r["flow_data"] = json.loads(r["flow_data"])
        r["selectors"] = json.loads(r["selectors"]) if r["selectors"] else None
        return r

    async def recall_flow(self, site: str, flow_type: str = "login") -> dict | None:
        return await self._get_flow(site, flow_type)

    # ── login profiles ───────────────────────────────────────────────────────

    async def remember_login(self, site: str, profile_path: str, email: str = "") -> None:
        db = await self._ensure()
        await db.execute(
            """INSERT INTO login_profiles(site_url, profile_path, email, last_used_at)
               VALUES(?,?,?,?)
               ON CONFLICT(site_url) DO UPDATE SET
                   profile_path=excluded.profile_path,
                   email=excluded.email,
                   last_used_at=excluded.last_used_at""",
            (site, profile_path, email, time.time()),
        )
        await db.commit()

    async def recall_login(self, site: str) -> dict | None:
        db = await self._ensure()
        async with db.execute(
            "SELECT * FROM login_profiles WHERE site_url=?", (site,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    # ── vectors ──────────────────────────────────────────────────────────────

    async def save_vector(
        self, site: str, text: str, embedding: list[float], metadata: dict | None = None
    ) -> None:
        db = await self._ensure()
        await db.execute(
            """INSERT INTO memory_vectors(site_url, text, embedding, metadata, created_at)
               VALUES(?,?,?,?,?)""",
            (site, text, json.dumps(embedding), json.dumps(metadata) if metadata else None, time.time()),
        )
        await db.commit()

    async def get_all_vectors(self) -> list[dict]:
        db = await self._ensure()
        async with db.execute(
            "SELECT id, site_url, text, embedding, metadata FROM memory_vectors ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["embedding"] = json.loads(d["embedding"])
            d["metadata"] = json.loads(d["metadata"]) if d["metadata"] else None
            result.append(d)
        return result

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
