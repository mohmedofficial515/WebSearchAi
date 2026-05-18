"""Unit tests for LLM providers (no real API calls)."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
import json


# ── MistralProvider ───────────────────────────────────────────────────────────

class TestMistralProvider:
    @pytest.fixture
    def provider(self):
        from src.llm.providers.mistral import MistralProvider
        p = MistralProvider.__new__(MistralProvider)
        p._api_key = "fake"
        p._client = MagicMock()
        p._client.chat = AsyncMock(return_value='{"ok": true}')
        p._client.chat_json = AsyncMock(return_value={"ok": True})
        p._client.vision = AsyncMock(return_value="vision result")
        p._client.vision_json = AsyncMock(return_value={"tags": []})
        p._client.close = AsyncMock()
        return p

    @pytest.mark.asyncio
    async def test_chat_json_delegates(self, provider):
        result = await provider.chat_json("sys", "user")
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_close_delegates(self, provider):
        await provider.close()
        provider._client.close.assert_awaited_once()


# ── OpenAIProvider ────────────────────────────────────────────────────────────

class TestOpenAIProvider:
    @pytest.fixture
    def provider(self):
        from src.llm.providers.openai import OpenAIProvider
        p = OpenAIProvider.__new__(OpenAIProvider)
        p._api_key = "fake"
        p._text_model = "gpt-4o-mini"
        p._vision_model = "gpt-4o"
        p._headers = {}
        return p

    @pytest.mark.asyncio
    async def test_chat_json_parses_response(self, provider):
        resp = json.dumps({"answer": 42})
        provider._post = AsyncMock(return_value={
            "choices": [{"message": {"content": resp}}]
        })
        result = await provider.chat_json("sys", "user")
        assert result["answer"] == 42

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, provider):
        provider._post = AsyncMock(return_value={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        emb = await provider.embed("hello")
        assert emb == [0.1, 0.2, 0.3]


# ── OllamaProvider ────────────────────────────────────────────────────────────

class TestOllamaProvider:
    @pytest.fixture
    def provider(self):
        from src.llm.providers.ollama import OllamaProvider
        return OllamaProvider(base_url="http://localhost:11434")

    def test_default_models(self, provider):
        assert provider._text_model == "llama3.2"
        assert provider._embed_model == "nomic-embed-text"


# ── auto get_provider ─────────────────────────────────────────────────────────

class TestGetProvider:
    def _make_settings(self, **kwargs):
        s = MagicMock()
        s.llm_provider = kwargs.get("llm_provider", "auto")
        s.mistral_api_key = kwargs.get("mistral_api_key", "")
        s.openai_api_key = kwargs.get("openai_api_key", "")
        s.anthropic_api_key = kwargs.get("anthropic_api_key", "")
        s.groq_api_key = kwargs.get("groq_api_key", "")
        s.gemini_api_key = kwargs.get("gemini_api_key", "")
        s.cohere_api_key = kwargs.get("cohere_api_key", "")
        s.openrouter_api_key = kwargs.get("openrouter_api_key", "")
        s.ollama_base_url = kwargs.get("ollama_base_url", "http://localhost:11434")
        s.mistral_text_model = "mistral-small-latest"
        s.mistral_vision_model = "pixtral-12b-2409"
        s.groq_text_model = "llama-3.1-8b-instant"
        s.gemini_text_model = "gemini-1.5-flash"
        s.cohere_text_model = "command-r"
        s.openrouter_text_model = "meta-llama/llama-3.1-8b-instruct:free"
        return s

    def test_auto_prefers_mistral_when_key_set(self):
        from src.llm.providers.auto import get_provider
        from src.llm.providers.mistral import MistralProvider
        from src.llm.providers.tracking import TrackingProvider
        settings = self._make_settings(mistral_api_key="abc123")
        provider = get_provider(settings)
        assert isinstance(provider, TrackingProvider)
        assert isinstance(provider._inner, MistralProvider)

    def test_auto_falls_back_to_ollama_when_no_keys(self):
        from src.llm.providers.auto import get_provider
        from src.llm.providers.ollama import OllamaProvider
        from src.llm.providers.tracking import TrackingProvider
        settings = self._make_settings()
        provider = get_provider(settings)
        assert isinstance(provider, TrackingProvider)
        assert isinstance(provider._inner, OllamaProvider)

    def test_explicit_openai_overrides_auto(self):
        from src.llm.providers.auto import get_provider
        from src.llm.providers.openai import OpenAIProvider
        from src.llm.providers.tracking import TrackingProvider
        settings = self._make_settings(
            llm_provider="openai",
            openai_api_key="sk-abc",
            mistral_api_key="mistral-key"
        )
        provider = get_provider(settings)
        assert isinstance(provider, TrackingProvider)
        assert isinstance(provider._inner, OpenAIProvider)


# ── Protocol compliance ───────────────────────────────────────────────────────

def test_mistral_provider_satisfies_protocol():
    from src.llm.providers.base import LLMClient
    from src.llm.providers.mistral import MistralProvider
    # Check protocol attributes exist
    for attr in ("chat", "chat_json", "vision", "vision_json", "embed", "close"):
        assert hasattr(MistralProvider, attr)
