"""Provider management — catalog, configuration test, live model listing.

The catalog (`_PROVIDER_CATALOG`) is the single source of truth the React
Settings panel renders. Each entry knows its key field on `Settings`,
its model field, signup URL, free-tier limits, and a curated `models`
list that gets enriched with `_MODEL_META` before serving.
"""

from __future__ import annotations

import time
from pathlib import Path

import httpx
from fastapi import APIRouter

from ...config import settings


router = APIRouter(prefix="/api/providers", tags=["providers"])

# Path to .env (project root). Computed once so save endpoints can write back.
ROOT = Path(__file__).resolve().parent.parent.parent.parent


# Model metadata: stars (1-5), speed (fast/medium/slow/local), vision support
_MODEL_META: dict[str, dict] = {
    # ── Groq ──
    "llama-3.1-8b-instant":            {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "llama-3.3-70b-versatile":         {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "llama-3.2-11b-vision-preview":    {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 128},
    "llama-3.2-90b-vision-preview":    {"stars": 5, "speed": "medium", "vision": True,  "ctx_k": 128},
    "llama-3.2-3b-preview":            {"stars": 2, "speed": "fast",   "vision": False, "ctx_k": 128},
    "gemma2-9b-it":                    {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 8},
    # ── Gemini ──
    "gemini-2.0-flash":                {"stars": 5, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-2.5-flash-preview-05-20":  {"stars": 5, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-1.5-flash":                {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-2.0-flash-exp":            {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 1048},
    "gemini-1.5-pro":                  {"stars": 5, "speed": "medium", "vision": True,  "ctx_k": 2097},
    # ── Cohere ──
    "command-r":                       {"stars": 3, "speed": "medium", "vision": False, "ctx_k": 128},
    "command-r-plus":                  {"stars": 4, "speed": "medium", "vision": False, "ctx_k": 128},
    "command-r7b-12-2024":             {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "command-a-03-2025":               {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 256},
    # ── OpenRouter free ──
    "meta-llama/llama-3.1-8b-instruct:free":     {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "meta-llama/llama-3.2-3b-instruct:free":     {"stars": 2, "speed": "fast",   "vision": False, "ctx_k": 128},
    "meta-llama/llama-3.3-70b-instruct:free":    {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "google/gemma-2-9b-it:free":                 {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 8},
    "google/gemma-3-12b-it:free":                {"stars": 4, "speed": "fast",   "vision": True,  "ctx_k": 128},
    "mistralai/mistral-7b-instruct:free":        {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "microsoft/phi-3-mini-128k-instruct:free":   {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 128},
    "qwen/qwen-2-7b-instruct:free":              {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "qwen/qwen3-8b:free":                        {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 128},
    "deepseek/deepseek-r1:free":                 {"stars": 5, "speed": "slow",   "vision": False, "ctx_k": 64},
    "deepseek/deepseek-chat-v3-0324:free":       {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 64},
    "nousresearch/hermes-3-llama-3.1-405b:free": {"stars": 5, "speed": "slow",   "vision": False, "ctx_k": 128},
    # ── Mistral ──
    "mistral-small-latest":  {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "mistral-large-latest":  {"stars": 5, "speed": "medium", "vision": False, "ctx_k": 128},
    "open-mistral-7b":       {"stars": 3, "speed": "fast",   "vision": False, "ctx_k": 32},
    "open-mixtral-8x7b":     {"stars": 4, "speed": "medium", "vision": False, "ctx_k": 32},
    "codestral-latest":      {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 256},
    "mistral-nemo":          {"stars": 4, "speed": "fast",   "vision": False, "ctx_k": 128},
    "pixtral-large-latest":  {"stars": 5, "speed": "slow",   "vision": True,  "ctx_k": 128},
    # ── OpenAI ──
    "gpt-4o-mini": {"stars": 4, "speed": "fast",   "vision": True, "ctx_k": 128},
    "gpt-4o":      {"stars": 5, "speed": "medium", "vision": True, "ctx_k": 128},
    # ── Anthropic ──
    "claude-haiku-4-5-20251001": {"stars": 4, "speed": "fast",   "vision": True, "ctx_k": 200},
    "claude-sonnet-4-6":         {"stars": 5, "speed": "medium", "vision": True, "ctx_k": 200},
    "claude-opus-4-7":           {"stars": 5, "speed": "slow",   "vision": True, "ctx_k": 200},
    # ── Ollama local ──
    "llama3.2":  {"stars": 3, "speed": "local", "vision": True,  "ctx_k": 128},
    "llama3.1":  {"stars": 4, "speed": "local", "vision": False, "ctx_k": 128},
    "mistral":   {"stars": 3, "speed": "local", "vision": False, "ctx_k": 32},
    "phi3":      {"stars": 3, "speed": "local", "vision": False, "ctx_k": 128},
    "gemma2":    {"stars": 3, "speed": "local", "vision": False, "ctx_k": 8},
    "qwen2.5":   {"stars": 4, "speed": "local", "vision": False, "ctx_k": 128},
}

_PROVIDER_CATALOG = [
    {
        "name": "groq",
        "label": "Groq",
        "emoji": "⚡",
        "tier": "free",
        "desc": "Ultra-fast open-source inference — fastest free option",
        "free_info": "14,400 req/day · 6K tokens/min",
        "signup_url": "https://console.groq.com",
        "models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "llama-3.2-11b-vision-preview",
            "llama-3.2-90b-vision-preview",
            "llama-3.2-3b-preview",
            "gemma2-9b-it",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "groq_api_key",
        "model_field": "groq_text_model",
        "key_placeholder": "gsk_...",
    },
    {
        "name": "gemini",
        "label": "Google Gemini",
        "emoji": "✨",
        "tier": "free",
        "desc": "Google's multimodal AI — vision + 1M token context",
        "free_info": "1,500 req/day · 15 req/min",
        "signup_url": "https://aistudio.google.com",
        "models": [
            "gemini-2.0-flash",
            "gemini-2.5-flash-preview-05-20",
            "gemini-1.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "gemini_api_key",
        "model_field": "gemini_text_model",
        "key_placeholder": "AIza...",
    },
    {
        "name": "cohere",
        "label": "Cohere",
        "emoji": "🧩",
        "tier": "free",
        "desc": "Best free embeddings — 100+ language multilingual model",
        "free_info": "1,000 calls/month (Trial key)",
        "signup_url": "https://cohere.com",
        "models": [
            "command-r",
            "command-r-plus",
            "command-r7b-12-2024",
            "command-a-03-2025",
        ],
        "supports_vision": False,
        "supports_embed": True,
        "key_field": "cohere_api_key",
        "model_field": "cohere_text_model",
        "key_placeholder": "...",
    },
    {
        "name": "openrouter",
        "label": "OpenRouter",
        "emoji": "🔀",
        "tier": "free",
        "desc": "Aggregates 200+ models — many permanently free (:free suffix). Models loaded live from API.",
        "free_info": "Unlimited on :free models",
        "signup_url": "https://openrouter.ai",
        "models": [
            "meta-llama/llama-3.1-8b-instruct:free",
            "meta-llama/llama-3.2-3b-instruct:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "google/gemma-2-9b-it:free",
            "google/gemma-3-12b-it:free",
            "mistralai/mistral-7b-instruct:free",
            "microsoft/phi-3-mini-128k-instruct:free",
            "qwen/qwen-2-7b-instruct:free",
            "qwen/qwen3-8b:free",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-chat-v3-0324:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "openrouter_api_key",
        "model_field": "openrouter_text_model",
        "key_placeholder": "sk-or-...",
    },
    {
        "name": "mistral",
        "label": "Mistral",
        "emoji": "🌬️",
        "tier": "paid",
        "desc": "Best-in-class European AI — vision + embeddings",
        "free_info": "Free trial credits at sign-up",
        "signup_url": "https://console.mistral.ai",
        "models": [
            "mistral-small-latest",
            "mistral-large-latest",
            "open-mistral-7b",
            "open-mixtral-8x7b",
            "codestral-latest",
            "mistral-nemo",
            "pixtral-large-latest",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "mistral_api_key",
        "model_field": "mistral_text_model",
        "key_placeholder": "...",
    },
    {
        "name": "openai",
        "label": "OpenAI",
        "emoji": "🤖",
        "tier": "paid",
        "desc": "GPT-4o family — industry standard",
        "free_info": "Pay-per-use, no free tier",
        "signup_url": "https://platform.openai.com",
        "models": [
            "gpt-4o-mini",
            "gpt-4o",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": "openai_api_key",
        "model_field": None,
        "key_placeholder": "sk-...",
    },
    {
        "name": "anthropic",
        "label": "Anthropic",
        "emoji": "🧠",
        "tier": "paid",
        "desc": "Claude family — best for long documents & reasoning",
        "free_info": "Pay-per-use, no free tier",
        "signup_url": "https://console.anthropic.com",
        "models": [
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-6",
            "claude-opus-4-7",
        ],
        "supports_vision": True,
        "supports_embed": False,
        "key_field": "anthropic_api_key",
        "model_field": None,
        "key_placeholder": "sk-ant-...",
    },
    {
        "name": "ollama",
        "label": "Ollama (Local)",
        "emoji": "🦙",
        "tier": "local",
        "desc": "Run any open-source model 100% locally — no API key needed",
        "free_info": "Completely free — runs on your machine",
        "signup_url": "https://ollama.com",
        "models": [
            "llama3.2",
            "llama3.1",
            "mistral",
            "phi3",
            "gemma2",
            "qwen2.5",
        ],
        "supports_vision": True,
        "supports_embed": True,
        "key_field": None,
        "model_field": None,
        "key_placeholder": None,
    },
]


_ALLOWED_SETTINGS = {
    "llm_provider",
    "mistral_api_key", "mistral_text_model",
    "openai_api_key",
    "anthropic_api_key",
    "groq_api_key", "groq_text_model",
    "gemini_api_key", "gemini_text_model",
    "cohere_api_key", "cohere_text_model",
    "openrouter_api_key", "openrouter_text_model",
    "ollama_base_url",
}


_OPENROUTER_FALLBACK_MODELS = [
    "meta-llama/llama-3.1-8b-instruct:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-2-9b-it:free",
    "google/gemma-3-12b-it:free",
    "mistralai/mistral-7b-instruct:free",
    "microsoft/phi-3-mini-128k-instruct:free",
    "qwen/qwen-2-7b-instruct:free",
    "qwen/qwen3-8b:free",
    "deepseek/deepseek-r1:free",
    "deepseek/deepseek-chat-v3-0324:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _key_hint(val: str) -> str:
    """Return first 6 chars + '...' or empty string."""
    if not val:
        return ""
    return val[:6] + "..." if len(val) > 6 else val


def _update_dotenv(updates: dict[str, str]) -> None:
    """Write/update key=VALUE pairs in .env — creates file if absent."""
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    written: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip().upper()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        new_lines.append(line)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("")
async def api_list_providers() -> dict:
    """Return provider catalog with current configuration status."""
    result = []
    for meta in _PROVIDER_CATALOG:
        key_field = meta["key_field"]
        model_field = meta["model_field"]
        current_key: str = getattr(settings, str(key_field), "") if key_field else ""
        current_model: str = getattr(settings, str(model_field), "") if model_field else ""
        enriched_models = []
        raw_models: list[str] = meta["models"]  # type: ignore[assignment]
        for m in raw_models:
            mm = _MODEL_META.get(
                m,
                {
                    "stars": 3,
                    "speed": "medium",
                    "vision": meta.get("supports_vision", False),
                    "ctx_k": 0,
                },
            )
            enriched_models.append({
                "id": m,
                "stars": mm["stars"],
                "speed": mm["speed"],
                "vision": mm["vision"],
                "ctx_k": mm["ctx_k"],
            })
        entry = {
            **meta,
            "models": enriched_models,
            "is_configured": bool(current_key) or meta["name"] == "ollama",
            "key_hint": _key_hint(current_key),
            "current_model": current_model,
        }
        result.append(entry)
    return {"active": settings.llm_provider, "providers": result}


@router.post("/save")
async def api_save_providers(body: dict) -> dict:
    """Persist provider settings to .env and update in-memory config."""
    safe = {k: str(v) for k, v in body.items() if k in _ALLOWED_SETTINGS and v is not None}
    _update_dotenv({k.upper(): v for k, v in safe.items()})
    for k, v in safe.items():
        try:
            setattr(settings, k, v)
        except Exception:  # noqa: BLE001 — pydantic raises a variety of types here
            pass
    return {"ok": True, "saved": sorted(safe.keys())}


@router.get("/test/{name}")
async def api_test_provider(name: str) -> dict:
    """Quick connectivity test — returns actual model reply."""
    from ...llm.providers.auto import make_named_provider

    try:
        provider = make_named_provider(name, settings)
        model_name = getattr(provider, "_text_model", name)
        start = time.time()
        reply = await provider.chat(
            [{"role": "user", "content": "Say hello and tell me your model name in one short sentence."}]
        )
        ms = int((time.time() - start) * 1000)
        await provider.close()
        return {"ok": True, "latency_ms": ms, "model": model_name, "reply": reply}
    except NotImplementedError as exc:
        return {"ok": False, "error": f"Not configured: {exc}"}
    except Exception as exc:  # noqa: BLE001 — provider SDKs raise many exception classes
        return {"ok": False, "error": str(exc)}


@router.get("/openrouter/models")
async def api_openrouter_models() -> dict:
    """Fetch live free model list from OpenRouter — no API key required."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"HTTP-Referer": "https://websearchai.local", "X-Title": "WebSearchAi"},
            )
            r.raise_for_status()
            data = r.json()

        free: list[dict] = []
        for m in data.get("data", []):
            model_id: str = m.get("id", "")
            pricing = m.get("pricing", {})
            prompt_price = str(pricing.get("prompt", "1"))
            completion_price = str(pricing.get("completion", "1"))
            is_free = model_id.endswith(":free") or (
                prompt_price in ("0", "0.0") and completion_price in ("0", "0.0")
            )
            if is_free:
                free.append({
                    "id": model_id,
                    "name": m.get("name", model_id),
                    "context_length": m.get("context_length", 0),
                    "supports_vision": any(
                        "image" in str(mod).lower()
                        for mod in m.get("architecture", {}).get("modality", "").split("+")
                    ),
                })

        free.sort(key=lambda x: x["id"])
        return {"ok": True, "source": "live", "models": free}

    except Exception as exc:  # noqa: BLE001 — network/JSON errors are heterogeneous
        fallback = [
            {"id": mid, "name": mid, "context_length": 0, "supports_vision": False}
            for mid in _OPENROUTER_FALLBACK_MODELS
        ]
        return {"ok": False, "source": "fallback", "error": str(exc), "models": fallback}


@router.get("/{name}/models")
async def api_provider_models(name: str) -> dict:
    """Fetch live model list from the named provider's API."""
    try:
        if name == "openrouter":
            return await api_openrouter_models()

        if name == "groq":
            key = getattr(settings, "groq_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                data = r.json()
            models = [
                {
                    "id": m["id"],
                    "name": m.get("id", ""),
                    "context_length": 0,
                    "supports_vision": "vision" in m.get("id", "").lower(),
                }
                for m in data.get("data", [])
                if not m.get("id", "").endswith("-whisper")
                and "whisper" not in m.get("id", "").lower()
            ]
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "gemini":
            key = getattr(settings, "gemini_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                )
                r.raise_for_status()
                data = r.json()
            models = []
            for m in data.get("models", []):
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                raw_name = m.get("name", "").replace("models/", "")
                models.append({
                    "id": raw_name,
                    "name": m.get("displayName", raw_name),
                    "context_length": m.get("inputTokenLimit", 0),
                    "supports_vision": True,
                })
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "cohere":
            key = getattr(settings, "cohere_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.cohere.com/v1/models",
                    headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                )
                r.raise_for_status()
                data = r.json()
            models = []
            for m in data.get("models", []):
                endpoints = m.get("endpoints", [])
                if "chat" not in endpoints and "generate" not in endpoints:
                    continue
                models.append({
                    "id": m.get("name", ""),
                    "name": m.get("name", ""),
                    "context_length": m.get("context_length", 0),
                    "supports_vision": False,
                })
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        if name == "mistral":
            key = getattr(settings, "mistral_api_key", "")
            if not key:
                return {"ok": False, "error": "No API key configured", "models": [], "source": "none"}
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                r.raise_for_status()
                data = r.json()
            models = [
                {
                    "id": m["id"],
                    "name": m.get("name", m["id"]),
                    "context_length": 0,
                    "supports_vision": "pixtral" in m.get("id", "").lower(),
                }
                for m in data.get("data", [])
            ]
            models.sort(key=lambda x: x["id"])
            return {"ok": True, "source": "live", "models": models}

        return {"ok": False, "error": f"No live model list for {name!r}", "models": [], "source": "none"}

    except Exception as exc:  # noqa: BLE001 — heterogeneous network/HTTP failures
        return {"ok": False, "source": "error", "error": str(exc), "models": []}
