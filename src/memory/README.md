# `src/memory/` — long-term agent memory

Reserved for **Phase 2**. See [`docs/ROADMAP.md`](../../docs/ROADMAP.md#phase-2--long-term-memory--skill-library).

Planned layout:
- `memory/store.py` — SQLite-backed key-value + JSON blob store at `outputs/memory.db`
- `memory/recall.py` — embedding similarity search via Mistral embed
- `memory/schema.sql` — tables: `sites`, `flows`, `selectors`, `login_profiles`

The contract (sketch):
```python
class Memory:
    async def remember_flow(self, site: str, flow: dict) -> None: ...
    async def recall_flow(self, site: str) -> dict | None: ...
    async def search(self, query: str, k: int = 5) -> list[dict]: ...
```

Until Phase 2 ships, the agent re-discovers selectors each run.
