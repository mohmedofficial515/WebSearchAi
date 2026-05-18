# `src/storage/` — persistence layer

Reserved for **Phase 6**: durable task storage.

Today: not used. Tasks live in the in-memory dict in `src/api/tasks.py`.

When Phase 6 lands:
- `storage/sqlite.py` — SQLite implementation of `TaskStore` for single-host deployments
- `storage/redis.py` — Redis-backed store for HA / multi-instance
- `storage/base.py` — `TaskStore` Protocol

Migration path:
1. Extract a `TaskStore` Protocol from `api/tasks.py`
2. Move the dict logic into `storage/memory.py`
3. Add SQLite implementation
4. Pick at startup via `STORAGE_BACKEND` env var
