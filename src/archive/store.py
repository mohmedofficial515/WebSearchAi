"""SQLite-backed task archive with TF-IDF similarity search.

Why TF-IDF and not embeddings?
  - Zero external dependency: works offline, no API key, no rate limits.
  - Deterministic and fast for the scale a personal agent hits (1k-100k
    tasks). Recomputing IDF on each search costs <50ms for that size.
  - Handles Arabic and English equally well — `\\w+` is Unicode-aware.
  - Easy to reason about: a search for "real estate Saudi 2026" matches
    a stored goal "top real estate platforms in Saudi Arabia 2026"
    because they share the rare tokens 'real', 'estate', 'saudi', '2026'.

If you later want true semantic embeddings, swap _score_corpus() to
call your LLM provider's embedding endpoint and store the vectors in
the embedding column we already reserved.
"""
from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite


_SCHEMA = """
CREATE TABLE IF NOT EXISTS task_archive (
    task_id          TEXT PRIMARY KEY,
    goal             TEXT NOT NULL,
    goal_normalized  TEXT NOT NULL,
    summary          TEXT,
    success          INTEGER NOT NULL DEFAULT 1,
    confidence       REAL,
    starting_url     TEXT,
    result_json      TEXT,
    plan_json        TEXT,
    extractions_json TEXT,
    embedding        TEXT,
    created_at       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_archive_created ON task_archive(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_archive_success ON task_archive(success);
"""


# ── Text normalization ───────────────────────────────────────────────────────

# Tiny stopword set in English + Arabic — keeps "real estate" and "real
# estate platforms" both matching the same archive entry even if one
# uses "the" / "في" / "and".
_STOP = frozenset(
    """
    a an the and or but if then so of to in on at for with by from as is are
    was were be been being do does did have has had can will would should
    what which who whom where when why how me my your you we us our this that
    these those it its them their he she they him her his
    في من على إلى عن مع هل ما ماذا كيف لماذا أين متى و أو ثم لكن أن إن كان
    كانت يكون هذا هذه ذلك تلك التي الذي اللذان اللتان الذين اللائي ال
    """.split()
)

# Arabic letter folding so "أحمد" / "احمد" / "إحمد" all collapse to the
# same token. This dramatically improves recall on Arabic queries.
_AR_FOLD = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
    }
)
_AR_DIACRITICS_RE = re.compile(r"[ؐ-ًؚ-ٟۖ-ۭ]")
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _normalize(text: str) -> str:
    """Lowercase, strip Arabic diacritics, fold confusables.
    Keeps Unicode word characters; everything else becomes whitespace."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = _AR_DIACRITICS_RE.sub("", t)
    t = t.translate(_AR_FOLD)
    return t.lower()


def _tokens(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(_normalize(text)) if w not in _STOP and len(w) > 1]


def _tfidf_score(query_tokens: list[str], doc_tokens: list[str], idf: dict[str, float]) -> float:
    """Cosine similarity over (sublinear) TF·IDF vectors. Returns 0..1."""
    if not query_tokens or not doc_tokens:
        return 0.0
    q_tf = Counter(query_tokens)
    d_tf = Counter(doc_tokens)
    # Vector lengths (over union — but unseen terms drop out of dot product anyway)
    q_norm = math.sqrt(sum(((1 + math.log(c)) * idf.get(w, 0.0)) ** 2 for w, c in q_tf.items()))
    d_norm = math.sqrt(sum(((1 + math.log(c)) * idf.get(w, 0.0)) ** 2 for w, c in d_tf.items()))
    if q_norm == 0 or d_norm == 0:
        return 0.0
    dot = 0.0
    for w, qc in q_tf.items():
        dc = d_tf.get(w)
        if not dc:
            continue
        qw = (1 + math.log(qc)) * idf.get(w, 0.0)
        dw = (1 + math.log(dc)) * idf.get(w, 0.0)
        dot += qw * dw
    return dot / (q_norm * d_norm)


# ── Records ──────────────────────────────────────────────────────────────────

@dataclass
class ArchiveRecord:
    task_id: str
    goal: str
    summary: str
    success: bool
    confidence: float
    starting_url: str | None
    extractions: list[str]
    plan: dict[str, Any] | None
    created_at: float

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "summary": self.summary,
            "success": self.success,
            "confidence": self.confidence,
            "starting_url": self.starting_url,
            "extractions": self.extractions,
            "plan": self.plan,
            "created_at": self.created_at,
        }


@dataclass
class Match:
    record: ArchiveRecord
    score: float
    # Human-readable "why this matched" string — surfaced in UI so users
    # can sanity-check that the retrieval isn't random.
    matched_terms: list[str]

    def to_dict(self) -> dict:
        return {
            **self.record.to_dict(),
            "score": round(self.score, 4),
            "matched_terms": self.matched_terms,
        }


# ── Store ────────────────────────────────────────────────────────────────────

class ArchiveStore:
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

    # ── Writes ──────────────────────────────────────────────────────────────

    async def save(
        self,
        task_id: str,
        goal: str,
        result: dict[str, Any],
    ) -> None:
        """Save a completed task. Idempotent — same task_id overwrites.

        Only successful tasks are normally archived (the agent guards
        this), but we don't enforce here so callers can keep a record
        of partial successes too if they want."""
        db = await self._ensure()
        plan = result.get("plan") if isinstance(result, dict) else None
        await db.execute(
            """INSERT OR REPLACE INTO task_archive(
                task_id, goal, goal_normalized, summary, success, confidence,
                starting_url, result_json, plan_json, extractions_json,
                embedding, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                goal,
                _normalize(goal),
                str(result.get("summary") or "") if isinstance(result, dict) else "",
                1 if isinstance(result, dict) and result.get("success") else 0,
                float(result.get("confidence") or 0.0) if isinstance(result, dict) else 0.0,
                (plan or {}).get("starting_url") if isinstance(plan, dict) else None,
                json.dumps(result, ensure_ascii=False, default=str),
                json.dumps(plan, ensure_ascii=False, default=str) if plan else None,
                json.dumps(result.get("extractions") or [], ensure_ascii=False)
                if isinstance(result, dict) else "[]",
                None,  # embedding — reserved for future use
                time.time(),
            ),
        )
        await db.commit()

    async def delete(self, task_id: str) -> bool:
        db = await self._ensure()
        cur = await db.execute("DELETE FROM task_archive WHERE task_id=?", (task_id,))
        await db.commit()
        return (cur.rowcount or 0) > 0

    async def clear(self) -> int:
        db = await self._ensure()
        cur = await db.execute("DELETE FROM task_archive")
        await db.commit()
        return cur.rowcount or 0

    # ── Reads ───────────────────────────────────────────────────────────────

    async def list(self, limit: int = 50, success_only: bool = False) -> list[ArchiveRecord]:
        db = await self._ensure()
        q = "SELECT * FROM task_archive"
        if success_only:
            q += " WHERE success=1"
        q += " ORDER BY created_at DESC LIMIT ?"
        async with db.execute(q, (limit,)) as cur:
            rows = await cur.fetchall()
        return [self._row_to_record(r) for r in rows]

    async def get(self, task_id: str) -> dict | None:
        """Return the full archived task including the raw result_json."""
        db = await self._ensure()
        async with db.execute(
            "SELECT * FROM task_archive WHERE task_id=?", (task_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["result"] = json.loads(d.pop("result_json")) if d.get("result_json") else None
        d["plan"] = json.loads(d.pop("plan_json")) if d.get("plan_json") else None
        d["extractions"] = json.loads(d.pop("extractions_json")) if d.get("extractions_json") else []
        d.pop("embedding", None)
        d.pop("goal_normalized", None)
        d["success"] = bool(d["success"])
        return d

    # ── Search ──────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.05,
        success_only: bool = True,
    ) -> list[Match]:
        """Rank archive entries by TF-IDF cosine similarity to `query`."""
        q_tokens = _tokens(query)
        if not q_tokens:
            return []

        db = await self._ensure()
        sql = "SELECT task_id, goal, goal_normalized, summary, success, confidence, starting_url, extractions_json, plan_json, created_at FROM task_archive"
        if success_only:
            sql += " WHERE success=1"
        async with db.execute(sql) as cur:
            rows = await cur.fetchall()

        if not rows:
            return []

        # Build the corpus once per search call. For 1000s of rows this
        # is microseconds; for 100k+ you'd want to cache the IDF.
        docs = [_tokens(r["goal_normalized"] or "") for r in rows]
        n_docs = len(docs)
        df: Counter = Counter()
        for d in docs:
            for w in set(d):
                df[w] += 1
        # IDF with +1 smoothing — keeps single-doc terms slightly weighted.
        idf = {w: math.log((n_docs + 1) / (c + 1)) + 1 for w, c in df.items()}

        out: list[Match] = []
        q_set = set(q_tokens)
        for row, doc_tokens in zip(rows, docs):
            score = _tfidf_score(q_tokens, doc_tokens, idf)
            if score < min_score:
                continue
            shared = [w for w in dict.fromkeys(doc_tokens) if w in q_set]  # preserve order, dedupe
            rec = self._row_to_record(row)
            out.append(Match(record=rec, score=score, matched_terms=shared[:8]))

        out.sort(key=lambda m: m.score, reverse=True)
        return out[:limit]

    async def find_similar(
        self,
        goal: str,
        threshold: float = 0.55,
    ) -> Match | None:
        """Top match if it scores at or above `threshold`. None otherwise.

        Threshold guide (empirical):
          0.95+ → effectively identical wording
          0.80  → same intent, slightly different phrasing
          0.55  → same topic; safe to suggest as "did you mean this?"
          <0.40 → unrelated
        """
        hits = await self.search(goal, limit=1, min_score=threshold, success_only=True)
        return hits[0] if hits else None

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _row_to_record(self, row: aiosqlite.Row) -> ArchiveRecord:
        d = dict(row)
        return ArchiveRecord(
            task_id=d["task_id"],
            goal=d["goal"],
            summary=d.get("summary") or "",
            success=bool(d.get("success") or 0),
            confidence=float(d.get("confidence") or 0.0),
            starting_url=d.get("starting_url"),
            extractions=json.loads(d.get("extractions_json")) if d.get("extractions_json") else [],
            plan=json.loads(d.get("plan_json")) if d.get("plan_json") else None,
            created_at=float(d.get("created_at") or 0.0),
        )

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None
