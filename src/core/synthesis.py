"""Final-answer synthesizer for the search-first agent.

Given the goal and the useful sources gathered during research, produce
a cited answer + confidence + self-critique. Single LLM call returning
strict JSON; defensive fallbacks so a hiccup never sinks the whole run.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


_SYNTH_SYSTEM = """You write the FINAL ANSWER for a research goal, citing the sources you were given.

You receive:
- GOAL: the user's question (in their own language)
- SOURCES: a list of {url, verdict, useful_facts} from pages we already judged useful.

Rules:
- Answer in the GOAL's language. If the goal is Arabic, answer in Arabic.
- Ground every concrete claim in at least one source URL. Do NOT invent facts not present in the sources.
- Cite by URL — short inline list, no markdown footnotes.
- Be concise: 2-6 sentences for simple goals; bullets for lists.
- If the sources contradict each other, say so explicitly.
- If the sources do NOT actually answer the goal, set confidence low and explain what's missing.

Reply with JSON ONLY:
{
  "answer": "<the answer text>",
  "citations": [{"url": "<source url>", "quote": "<short supporting quote or fact>"}],
  "confidence": <0..1>,
  "caveats": "<short or empty>"
}"""


_CRITIQUE_SYSTEM = """You critique a draft research answer.

You receive:
- GOAL
- DRAFT ANSWER
- CITATIONS

Decide:
- does the draft directly address the goal? (true/false)
- are the citations actually supporting it? (true/false)
- a final adjusted confidence (0..1).
- one sentence of feedback in the goal's language.

Reply with JSON ONLY:
{"addresses_goal": <bool>, "well_cited": <bool>, "final_confidence": <0..1>, "feedback": "<short>"}"""


@dataclass
class Citation:
    url: str
    quote: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Synthesis:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    caveats: str = ""
    feedback: str = ""
    addresses_goal: bool = True
    well_cited: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence,
            "caveats": self.caveats,
            "feedback": self.feedback,
            "addresses_goal": self.addresses_goal,
            "well_cited": self.well_cited,
        }


class Synthesizer:
    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def synthesize(
        self,
        goal: str,
        sources: list[dict[str, Any]],
    ) -> Synthesis:
        """Produce a cited answer from {url, verdict, useful_facts} sources.

        `sources` is the list of pages whose ContentVerdict.is_useful was True.
        """
        if not sources:
            return Synthesis(
                answer="",
                confidence=0.0,
                caveats="No useful sources were collected.",
                addresses_goal=False,
                well_cited=False,
            )

        blocks: list[str] = []
        for s in sources:
            url = str(s.get("url") or "").strip()
            verdict = str(s.get("verdict") or "").strip()
            facts = s.get("useful_facts") or []
            if not isinstance(facts, list):
                facts = []
            facts_text = "\n      - " + "\n      - ".join(str(f).strip() for f in facts[:8] if str(f).strip())
            blocks.append(f"- url: {url}\n    verdict: {verdict}\n    useful_facts:{facts_text}")
        user = f"GOAL: {goal}\n\nSOURCES:\n" + "\n".join(blocks)

        # ── First pass: draft answer ─────────────────────────────────────
        draft: dict[str, Any] = {}
        try:
            data = await self._llm.chat_json(_SYNTH_SYSTEM, user)
            if isinstance(data, dict):
                draft = data
        except Exception:
            draft = {}

        answer = str(draft.get("answer") or "").strip()
        citations_raw = draft.get("citations") or []
        if not isinstance(citations_raw, list):
            citations_raw = []
        citations: list[Citation] = []
        for c in citations_raw:
            if not isinstance(c, dict):
                continue
            url = str(c.get("url") or "").strip()
            if not url:
                continue
            citations.append(Citation(url=url, quote=str(c.get("quote") or "").strip()[:400]))
        confidence = _clamp01(_to_float(draft.get("confidence"), 0.0))
        caveats = str(draft.get("caveats") or "").strip()

        if not answer:
            # Build a tiny fallback so we never return totally empty:
            # concatenated facts with URLs. Marks confidence low.
            fallback_lines = []
            for s in sources[:3]:
                url = str(s.get("url") or "").strip()
                facts = s.get("useful_facts") or []
                if facts:
                    fallback_lines.append(f"- {facts[0]} ({url})")
            answer = "\n".join(fallback_lines) or "(synthesizer produced no output)"
            confidence = max(confidence, 0.15)
            caveats = (caveats + " | Fallback synthesis used.").strip(" |")

        # ── Second pass: self-critique adjusts confidence ────────────────
        addresses = True
        well_cited = bool(citations)
        feedback = ""
        try:
            cite_text = "\n".join(f"- {c.url}: {c.quote[:120]}" for c in citations) or "(none)"
            critique_user = (
                f"GOAL: {goal}\n\nDRAFT ANSWER:\n{answer}\n\nCITATIONS:\n{cite_text}"
            )
            crit = await self._llm.chat_json(_CRITIQUE_SYSTEM, critique_user)
            if isinstance(crit, dict):
                addresses = bool(crit.get("addresses_goal", True))
                well_cited = bool(crit.get("well_cited", well_cited))
                fc = crit.get("final_confidence")
                if fc is not None:
                    confidence = _clamp01(_to_float(fc, confidence))
                feedback = str(crit.get("feedback") or "").strip()
        except Exception:
            # If critic fails, keep the draft as-is.
            pass

        return Synthesis(
            answer=answer,
            citations=citations,
            confidence=confidence,
            caveats=caveats,
            feedback=feedback,
            addresses_goal=addresses,
            well_cited=well_cited,
        )


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v
