"""Natural-language intent routing.

The user types one sentence in the search box. We decide whether it's:
  * research      → SearchAgent / Agent.run (default)
  * signup        → skill_signup
  * temp_signup   → skill_temp_signup_persist (persistent profile)
  * login         → skill_login
  * explore       → skill_explore
  * clone         → skill_clone
  * components    → skill_find_components
  * design_tokens → skill_design_tokens

The router is intentionally rule-based: a tiny LLM call to classify
intent is overkill for the kinds of phrasings users actually type, and
it keeps the dispatch deterministic and offline-friendly. Patterns
cover Arabic + English variants.

Public surface:
    intent = detect_intent(goal)             # → Intent dataclass
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://[^\s)\]\"'<>]+", re.IGNORECASE)


# Tokens that signal "open / browse / explore a site"
_EXPLORE_PATTERNS = [
    # Arabic
    r"حلل\s+(الموقع|الصفحة|هذا)", r"استكشف\s+(الموقع|الصفحة)",
    r"اعطني\s+(تقرير|تحليل)\s+(للموقع|للصفحة)",
    r"افحص\s+(الموقع|هذا)",
    # English
    r"\bexplore\s+(this|the)\s+(site|page|url)\b",
    r"\banalyz[es]\s+(this|the)\s+(site|page|url)\b",
    r"\baudit\s+(this|the)\s+(site|page)\b",
]

# Login intent
_LOGIN_PATTERNS = [
    r"سجّ?ل\s+الدخول", r"ادخل\s+(إلى|الى|في)\s+حسابي", r"تسجيل\s+الدخول",
    r"\blog\s*in\s+to\b", r"\bsign\s*in\s+to\b", r"\blogin\s+to\b",
]

# Signup (with persistent profile)
_TEMP_SIGNUP_PATTERNS = [
    r"أنشئ\s+لي\s+حساب\s+(جديد|مؤقت|وهمي)",
    r"سجّ?ل\s+لي\s+حساب", r"حساب\s+(مؤقت|وهمي)",
    r"إنشاء\s+حساب", r"اعمل\s+حساب",
    r"\bcreate\s+(a\s+)?(temp|temporary|disposable|fake)\s+account",
    r"\bsign\s*up\s+for\s+me",
    r"\bregister\s+(me|a\s+new\s+account)\b",
]

# Plain signup (no persistent profile)
_SIGNUP_PATTERNS = [
    r"\bsign\s*up\s+(at|on|to)\b",
    r"اشترك\s+(في|على)",
]

# Clone / replicate
_CLONE_PATTERNS = [
    r"انسخ\s+(هذه|هذا|الصفحة|الموقع)", r"ابني?\s+نسخة\s+من",
    r"اعمل?\s+نسخة\s+(من|طبق\s+الأصل)",
    r"\bclone\s+(this|the)\s+(page|site)\b",
    r"\brebuild\s+(this|the)\s+(page|site)\b",
    r"\bcopy\s+(this|the)\s+(page|site)\b",
]

# Find UI components
_COMPONENTS_PATTERNS = [
    r"(ابحث|اعثر|اجلب)\s+(عن\s+)?(مكوّ?نات|مكونات|تصاميم)",
    r"معرض\s+مكوّ?نات",
    r"\bfind\s+(ui\s+)?(components|widgets|patterns)\b",
    r"\b(react|tailwind|bootstrap|vue)\s+(components|navbar|cards|hero)\b",
    r"\bcomponent\s+gallery\b",
]

# Interactive design agent (asks questions before building)
_DESIGN_AGENT_PATTERNS = [
    r"صمّ?م\s+لي\b", r"اصمّ?م\s+لي\b",
    r"أنشئ\s+تصميم\s+تفاعلي", r"تصميم\s+تفاعلي",
    r"وكيل\s+التصميم", r"ابدأ\s+تصميم",
    r"\bdesign\s+(for\s+me|agent|interactive|wizard)\b",
    r"\b/design\b",
]

# Design tokens
_TOKENS_PATTERNS = [
    r"استخرج\s+(الألوان|الخطوط|لوحة)",
    r"لوحة\s+ألوان", r"خطوط\s+الموقع",
    r"\bextract\s+(palette|colors?|fonts?|tokens?)\b",
    r"\bdesign\s+tokens?\b",
    r"\bcolor\s+palette\b",
]

# Conversational / greeting — answered by direct LLM chat, no web browsing needed
_CHAT_PATTERNS = [
    # Arabic greetings (full message = greeting only)
    r"^(مرحبا|مرحبًا|مرحباً|أهلاً?|اهلاً?|السلام عليكم|وعليكم السلام|هلا|يا هلا|حياك)\s*[!؟.,\s]*$",
    r"^(كيف حال(ك|كم|تك)?|كيفك|كيف الحال|شو عامل|ما أخبارك|ايش أخبارك)\s*[!؟.,\s]*$",
    r"^(صباح الخير|صباح النور|مساء الخير|مساء النور|تصبح على خير|نهارك سعيد)\s*[!؟.,\s]*$",
    r"^(شكراً?|شكرا جزيلاً?|ممنون|متشكر|يسلموا?|مشكور|الله يسلمك)\s*[!؟.,\s]*$",
    # Arabic identity / capability questions
    r"^(من أنت|ما اسمك|ماذا تفعل|ما هو دورك|أخبرني عن نفسك|ما قدراتك|ما الذي تستطيع فعله|ماذا تستطيع|ما هي إمكاناتك)\s*[!؟.,\s]*$",
    # English greetings (full message = greeting only)
    r"^(hi|hello|hey|howdy|greetings|yo)\s*[!?.,\s]*$",
    r"^good\s+(morning|evening|afternoon|day|night)\s*[!?.,\s]*$",
    r"^(thanks?|thank you|thx|ty|cheers|much appreciated)\s*[!?.,\s]*$",
    r"^(how are you|how're you|how are you doing|how's it going|what's up|sup)\s*[!?.,\s]*$",
    r"^(who are you|what are you|what's your name|tell me about yourself|what can you do)\s*[!?.,\s]*$",
]


# Compile once. Each entry: (compiled_regex, intent_name).
def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


_RULES: list[tuple[list[re.Pattern[str]], str]] = [
    # Chat must be first so greetings aren't hijacked by research fallback
    (_compile(_CHAT_PATTERNS), "chat"),
    (_compile(_TEMP_SIGNUP_PATTERNS), "temp_signup"),
    (_compile(_SIGNUP_PATTERNS), "signup"),
    (_compile(_LOGIN_PATTERNS), "login"),
    (_compile(_CLONE_PATTERNS), "clone"),
    (_compile(_COMPONENTS_PATTERNS), "components"),
    (_compile(_TOKENS_PATTERNS), "design_tokens"),
    (_compile(_DESIGN_AGENT_PATTERNS), "design_agent"),
    (_compile(_EXPLORE_PATTERNS), "explore"),
]


@dataclass
class Intent:
    """Routing decision for a natural-language goal."""
    kind: str                            # chat | research | signup | temp_signup | login | explore | clone | components | design_tokens
    goal: str                            # cleaned goal text
    url: str | None = None               # extracted http(s) URL if any
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0              # 0..1 — how sure are we

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "goal": self.goal,
            "url": self.url,
            "params": self.params,
            "confidence": self.confidence,
        }


def _extract_url(text: str) -> str | None:
    m = _URL_RE.search(text or "")
    if not m:
        return None
    url = m.group(0).rstrip(".,;:)]>")
    # Validate it parses as a URL.
    try:
        u = urlparse(url)
        if u.scheme in ("http", "https") and u.netloc:
            return url
    except Exception:
        pass
    return None


def _extract_credentials(text: str) -> dict[str, str]:
    """Pull `email: x`, `password: y`, `as <user>` style hints from the prompt.

    Used only by login intent — signup never needs caller-supplied creds.
    """
    out: dict[str, str] = {}
    m = re.search(r"(?:email|ايميل|بريد)[:\s]+([^\s,،]+@[^\s,،]+)", text, re.IGNORECASE)
    if m:
        out["email"] = m.group(1).strip()
    m = re.search(r"(?:password|كلمة\s+(?:السر|المرور))[:\s]+(\S+)", text, re.IGNORECASE)
    if m:
        out["password"] = m.group(1).strip()
    m = re.search(r"\bas\s+([\w.\-+]+@[\w.\-+]+)", text, re.IGNORECASE)
    if m and "email" not in out:
        out["email"] = m.group(1).strip()
    return out


def detect_intent(goal: str) -> Intent:
    """Classify a natural-language goal.

    Heuristics:
      * If the text matches a skill pattern → that skill (with extracted URL).
      * If it has a literal URL but no skill pattern → research (the agent's
        normal URL-aware flow handles 'summarize https://...' correctly).
      * Otherwise → research.

    We deliberately require BOTH a pattern match and (for most skills) a URL
    so plain research questions about a topic don't get hijacked. The only
    skill that fires without a URL is `components` (gallery search) and
    `temp_signup` when the user supplies the site name without a URL.
    """
    g = (goal or "").strip()
    if not g:
        return Intent(kind="research", goal=g, confidence=0.0)

    url = _extract_url(g)

    for patterns, name in _RULES:
        for p in patterns:
            if p.search(g):
                # Chat never needs a URL — fire immediately.
                if name == "chat":
                    return Intent(kind="chat", goal=g, url=None, confidence=0.95)
                # Skills that REQUIRE a URL — bail to research if missing.
                if name in {"login", "explore", "clone", "design_tokens"} and not url:
                    continue
                params: dict[str, Any] = {}
                if name in {"signup", "temp_signup"}:
                    # try to find an explicit full-name hint
                    fn = re.search(r"(?:full\s*name|اسمي|الاسم)[:\s]+([^\n,،]+)", g, re.IGNORECASE)
                    if fn:
                        params["full_name"] = fn.group(1).strip()[:80]
                if name == "login":
                    params.update(_extract_credentials(g))
                if name == "components":
                    # Strip the verb prefix so the query is the topic only.
                    q = re.sub(
                        r"^(ابحث|اعثر|اجلب)\s+(عن\s+)?(مكوّ?نات|مكونات|تصاميم)\s*",
                        "",
                        g,
                        flags=re.IGNORECASE,
                    )
                    q = re.sub(r"^find\s+(ui\s+)?(components|widgets|patterns)\s*",
                               "", q, flags=re.IGNORECASE).strip() or g
                    params["query"] = q
                return Intent(kind=name, goal=g, url=url, params=params, confidence=0.85)

    return Intent(kind="research", goal=g, url=url, confidence=1.0)
