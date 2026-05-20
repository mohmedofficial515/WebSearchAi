"""OpenRouter LLM provider — aggregates 200+ models, many permanently free.

Free tier: Models ending in `:free` are always free (no rate-limit tricks)
Sign up:   https://openrouter.ai  → Create account → Keys
Free models (as of 2026):
  - meta-llama/llama-3.1-8b-instruct:free   → Llama 3.1 8B
  - meta-llama/llama-3.2-3b-instruct:free   → Llama 3.2 3B (lightweight)
  - google/gemma-2-9b-it:free               → Google Gemma 2 9B
  - mistralai/mistral-7b-instruct:free       → Mistral 7B
  - microsoft/phi-3-mini-128k-instruct:free  → Phi-3 Mini 128K context
  - qwen/qwen-2-7b-instruct:free            → Qwen 2 7B
  - deepseek/deepseek-r1:free               → DeepSeek R1 (reasoning)
Note: Add ":free" suffix to any model name to use the free version.
"""
from __future__ import annotations
import base64
import json
import re
import httpx

_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_TEXT_MODEL = "meta-llama/llama-3.1-8b-instruct:free"

FREE_MODELS = [
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


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class OpenRouterProvider:
    supports_tools = False

    """OpenRouter cloud provider — OpenAI-compatible aggregator API."""

    def __init__(self, api_key: str, text_model: str = _DEFAULT_TEXT_MODEL) -> None:
        self._api_key = api_key
        self._text_model = text_model
        self._embed_model = "unsupported"
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://websearchai.local",
            "X-Title": "WebSearchAi",
        }

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{_BASE}{path}", json=body, headers=self._headers)
            r.raise_for_status()
            return r.json()

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **_) -> str:
        body: dict = {"model": self._text_model, "messages": messages}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = await self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"]

    async def chat_json(self, system: str, user: str, **_) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return _safe_json(await self.chat(msgs, json_mode=True))

    async def vision(self, prompt: str, image_bytes: bytes, **_) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        body = {
            "model": self._text_model,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
        }
        data = await self._post("/chat/completions", body)
        return data["choices"][0]["message"]["content"]

    async def vision_json(self, prompt: str, image_bytes: bytes, **_) -> dict:
        return _safe_json(await self.vision(prompt, image_bytes))

    async def embed(self, text: str, **_) -> list[float]:
        raise NotImplementedError(
            "OpenRouter does not provide embeddings — use Gemini or Cohere instead"
        )

    async def close(self) -> None:
        pass
