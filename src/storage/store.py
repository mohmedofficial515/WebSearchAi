"""SQLite-backed persistent task storage."""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any
import aiosqlite

# Import these from tasks.py — but to avoid circular imports at the type level
# we define lightweight type aliases here and cast at runtime
_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    params TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
"""


class TaskStore:
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

    async def save_task(self, task_id: str, kind: str, params: dict, status: str) -> None:
        db = await self._ensure()
        now = time.time()
        await db.execute(
            """INSERT OR REPLACE INTO tasks(task_id, kind, params, status, created_at, updated_at)
               VALUES(?,?,?,?,?,?)""",
            (task_id, kind, json.dumps(params), status, now, now),
        )
        await db.commit()

    async def update_status(
        self,
        task_id: str,
        status: str,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        db = await self._ensure()
        await db.execute(
            """UPDATE tasks SET status=?, result=?, error=?, updated_at=?
               WHERE task_id=?""",
            (
                status,
                json.dumps(result) if result is not None else None,
                error,
                time.time(),
                task_id,
            ),
        )
        await db.commit()

    async def load_task(self, task_id: str) -> dict | None:
        db = await self._ensure()
        async with db.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["params"] = json.loads(d["params"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d

    async def list_tasks(self, limit: int = 100, kind: str | None = None) -> list[dict]:
        db = await self._ensure()
        if kind:
            query = "SELECT * FROM tasks WHERE kind=? ORDER BY created_at DESC LIMIT ?"
            args = (kind, limit)
        else:
            query = "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?"
            args = (limit,)
        async with db.execute(query, args) as cur:
            rows = await cur.fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["params"] = json.loads(d["params"])
            d["result"] = json.loads(d["result"]) if d["result"] else None
            result.append(d)
        return result

    async def delete_task(self, task_id: str) -> None:
        db = await self._ensure()
        await db.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
        await db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
