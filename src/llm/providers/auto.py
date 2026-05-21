"""Auto-select LLM provider based on available API keys.

Priority chain (explicit → auto-detect):
  deepseek → mistral → openai → anthropic → groq → gemini → cohere → openrouter → ollama

DeepSeek leads the auto chain because it's the project's preferred free
provider (talks to chat.deepseek.com via a Node bridge — no API key, just
a captured browser auth token). Falls through to the others if no token.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import Settings
    from .base import LLMClient


def _make_provider(settings: "Settings") -> "LLMClient":
    """Build the raw (un-wrapped) provider from settings."""
    provider = getattr(settings, "llm_provider", "auto")

    # ── explicit selection ────────────────────────────────────────────────────
    if provider == "deepseek":
        from .deepseek import DeepSeekProvider
        return DeepSeekProvider(
            token=getattr(settings, "deepseek_user_token", ""),
            thinking=getattr(settings, "deepseek_thinking", False),
        )
    if provider == "chatgpt":
        from .chatgpt import ChatGPTProvider
        return ChatGPTProvider(model=getattr(settings, "chatgpt_model", "auto"))
    if provider == "mistral":
        from .mistral import MistralProvider
        return MistralProvider(
            api_key=settings.mistral_api_key,
            text_model=settings.mistral_text_model,
            vision_model=settings.mistral_vision_model,
        )
    if provider == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key)
    if provider == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if provider == "groq":
        from .groq import GroqProvider
        return GroqProvider(
            api_key=settings.groq_api_key,
            text_model=settings.groq_text_model,
        )
    if provider == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            text_model=settings.gemini_text_model,
        )
    if provider == "cohere":
        from .cohere import CohereProvider
        return CohereProvider(
            api_key=settings.cohere_api_key,
            text_model=settings.cohere_text_model,
        )
    if provider == "openrouter":
        from .openrouter import OpenRouterProvider
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            text_model=settings.openrouter_text_model,
        )
    if provider == "ollama":
        from .ollama import OllamaProvider
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            text_model=getattr(settings, "ollama_text_model", "llama3.2"),
            vision_model=getattr(settings, "ollama_vision_model", "llava"),
        )

    # ── auto-detect by available API keys ────────────────────────────────────
    # DeepSeek wins when the user has captured a web-session token — no
    # API key needed, free tier, and it's the project's preferred provider.
    if getattr(settings, "deepseek_user_token", ""):
        from .deepseek import DeepSeekProvider
        return DeepSeekProvider(
            token=settings.deepseek_user_token,
            thinking=getattr(settings, "deepseek_thinking", False),
        )
    if getattr(settings, "mistral_api_key", ""):
        from .mistral import MistralProvider
        return MistralProvider(
            api_key=settings.mistral_api_key,
            text_model=settings.mistral_text_model,
            vision_model=settings.mistral_vision_model,
        )
    if getattr(settings, "openai_api_key", ""):
        from .openai import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key)
    if getattr(settings, "anthropic_api_key", ""):
        from .anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if getattr(settings, "groq_api_key", ""):
        from .groq import GroqProvider
        return GroqProvider(
            api_key=settings.groq_api_key,
            text_model=getattr(settings, "groq_text_model", "llama-3.1-8b-instant"),
        )
    if getattr(settings, "gemini_api_key", ""):
        from .gemini import GeminiProvider
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            text_model=getattr(settings, "gemini_text_model", "gemini-1.5-flash"),
        )
    if getattr(settings, "cohere_api_key", ""):
        from .cohere import CohereProvider
        return CohereProvider(
            api_key=settings.cohere_api_key,
            text_model=getattr(settings, "cohere_text_model", "command-r"),
        )
    if getattr(settings, "openrouter_api_key", ""):
        from .openrouter import OpenRouterProvider
        return OpenRouterProvider(
            api_key=settings.openrouter_api_key,
            text_model=getattr(settings, "openrouter_text_model", "meta-llama/llama-3.1-8b-instruct:free"),
        )

    from .ollama import OllamaProvider
    return OllamaProvider(base_url=getattr(settings, "ollama_base_url", "http://localhost:11434"))


def _provider_name(p: "LLMClient") -> str:
    return type(p).__name__.replace("Provider", "").lower()


def get_provider(settings: "Settings") -> "LLMClient":
    """Return a cost-tracked LLM client wrapped in TrackingProvider."""
    from .tracking import TrackingProvider

    raw = _make_provider(settings)
    return TrackingProvider(raw, _provider_name(raw))


def make_named_provider(name: str, settings: "Settings") -> "LLMClient":
    """Build a specific provider by name — used for connection testing."""
    builders = {
        "deepseek": lambda: _make_deepseek(settings),
        "chatgpt": lambda: _make_chatgpt(settings),
        "groq": lambda: _make_groq(settings),
        "gemini": lambda: _make_gemini(settings),
        "cohere": lambda: _make_cohere(settings),
        "openrouter": lambda: _make_openrouter(settings),
        "mistral": lambda: _make_mistral(settings),
        "openai": lambda: _make_openai(settings),
        "anthropic": lambda: _make_anthropic(settings),
        "ollama": lambda: _make_ollama(settings),
    }
    if name not in builders:
        raise ValueError(f"Unknown provider: {name!r}")
    return builders[name]()


def _make_deepseek(s):
    from .deepseek import DeepSeekProvider
    return DeepSeekProvider(
        token=getattr(s, "deepseek_user_token", ""),
        thinking=getattr(s, "deepseek_thinking", False),
    )

def _make_chatgpt(s):
    from .chatgpt import ChatGPTProvider
    return ChatGPTProvider(model=getattr(s, "chatgpt_model", "auto"))

def _make_groq(s):
    from .groq import GroqProvider
    return GroqProvider(api_key=s.groq_api_key, text_model=s.groq_text_model)

def _make_gemini(s):
    from .gemini import GeminiProvider
    return GeminiProvider(api_key=s.gemini_api_key, text_model=s.gemini_text_model)

def _make_cohere(s):
    from .cohere import CohereProvider
    return CohereProvider(api_key=s.cohere_api_key, text_model=s.cohere_text_model)

def _make_openrouter(s):
    from .openrouter import OpenRouterProvider
    return OpenRouterProvider(api_key=s.openrouter_api_key, text_model=s.openrouter_text_model)

def _make_mistral(s):
    from .mistral import MistralProvider
    return MistralProvider(api_key=s.mistral_api_key, text_model=s.mistral_text_model, vision_model=s.mistral_vision_model)

def _make_openai(s):
    from .openai import OpenAIProvider
    return OpenAIProvider(api_key=s.openai_api_key)

def _make_anthropic(s):
    from .anthropic import AnthropicProvider
    return AnthropicProvider(api_key=s.anthropic_api_key)

def _make_ollama(s):
    from .ollama import OllamaProvider
    return OllamaProvider(
        base_url=s.ollama_base_url,
        text_model=getattr(s, "ollama_text_model", "llama3.2"),
        vision_model=getattr(s, "ollama_vision_model", "llava"),
    )
