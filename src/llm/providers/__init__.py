"""LLM provider implementations.

Usage:
    from src.llm.providers import get_provider
    from src.config import settings
    llm = get_provider(settings)
    result = await llm.chat_json(system_prompt, user_prompt)
"""
from __future__ import annotations

from .base import LLMClient
from .mistral import MistralProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider
from .groq import GroqProvider
from .gemini import GeminiProvider
from .cohere import CohereProvider
from .openrouter import OpenRouterProvider
from .ollama import OllamaProvider
from .tracking import TrackingProvider
from .failover import FailoverProvider
from .auto import get_provider, make_named_provider

__all__ = [
    "LLMClient",
    "MistralProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GroqProvider",
    "GeminiProvider",
    "CohereProvider",
    "OpenRouterProvider",
    "OllamaProvider",
    "TrackingProvider",
    "FailoverProvider",
    "get_provider",
    "make_named_provider",
]
