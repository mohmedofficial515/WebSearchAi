"""Centralized configuration loaded from .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM provider ─────────────────────────────────────────────────────────
    # auto | mistral | openai | anthropic | groq | gemini | cohere | openrouter | ollama
    llm_provider: str = "auto"

    # Mistral — https://console.mistral.ai  (free trial credits)
    mistral_api_key: str = ""
    mistral_text_model: str = "mistral-small-latest"
    mistral_vision_model: str = "pixtral-12b-2409"

    # OpenAI — https://platform.openai.com
    openai_api_key: str = ""

    # Anthropic — https://console.anthropic.com
    anthropic_api_key: str = ""

    # Groq — FREE: 14,400 req/day · https://console.groq.com
    groq_api_key: str = ""
    groq_text_model: str = "llama-3.1-8b-instant"

    # Google Gemini — FREE: 1,500 req/day · https://aistudio.google.com
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-1.5-flash"

    # Cohere — FREE: 1,000 calls/month · https://cohere.com
    cohere_api_key: str = ""
    cohere_text_model: str = "command-r"

    # OpenRouter — FREE models with :free suffix · https://openrouter.ai
    openrouter_api_key: str = ""
    openrouter_text_model: str = "meta-llama/llama-3.1-8b-instruct:free"

    # Ollama — local, completely free · https://ollama.com
    ollama_base_url: str = "http://localhost:11434"

    browser_headless: bool = False
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    browser_timeout: int = 30000
    browser_viewport_width: int = 1366
    browser_viewport_height: int = 768

    # When true, use the installed Google Chrome binary (channel="chrome")
    # so the TLS / JA4 fingerprint matches a real browser. Falls back to
    # bundled Chromium if Chrome is not present on the machine.
    use_chrome_channel: bool = True

    # Locale + timezone the browser should advertise. Match these to the
    # IP geolocation so headers and JS-exposed values stay consistent.
    browser_locale: str = "en-US"
    browser_timezone: str = "America/New_York"

    # patchright already patches navigator.* at binary level — keep this
    # off unless you want to layer an extra JS init script (usually a bad
    # idea: double-patching creates detectable inconsistencies).
    enable_stealth: bool = False

    min_action_delay_ms: int = 300
    max_action_delay_ms: int = 1200
    human_typing_wpm: int = 240

    # ── Search backend ───────────────────────────────────────────────────────
    # Order to try: "tavily" → "ddgs" → "browser" (scrape Bing as last resort).
    search_backend: str = "auto"   # auto | tavily | ddgs | browser
    tavily_api_key: str = ""
    brave_search_api_key: str = ""
    search_max_results: int = 12

    # ── Search-first agentic research ───────────────────────────────────────
    # When a goal contains no literal http(s) URL we route it through the
    # SearchAgent: generate queries → search → rank → critique → visit
    # top-K → judge content → (re-search if empty) → synthesize cited answer.
    # Defaults below favor a deeper, more thorough report (more queries,
    # more visits, more re-search rounds) over latency — flip them down
    # in .env if you need fast turnaround.
    research_enabled: bool = True            # master switch
    research_max_queries: int = 7            # diverse angles generated per round
    research_max_candidates: int = 6         # how many ranked URLs to visit
    research_min_useful_sources: int = 4     # stop synthesizing after N good pages
    research_max_re_search: int = 3          # extra search rounds if results were weak
    research_relevance_threshold: float = 0.55  # ContentVerdict.score to accept a page
    research_heuristic_weight: float = 0.4   # weight on heuristic vs LLM in final ranking
    research_extract_chars: int = 14000      # how much page text to feed the critic

    # When true, every research run starts fresh and never seeds the
    # planner with hints from the archive. Site-flow memory (login
    # cookies, captured form-fills) is still used. Set false to allow
    # cached "you've answered something similar" hints back in.
    research_fresh_runs: bool = True

    max_steps_per_task: int = 40
    max_retries_per_step: int = 3

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    output_dir: str = "./outputs"
    log_level: str = "INFO"

    http_proxy: str | None = None

    # Auth (Phase 8) — disabled by default; set AUTH_ENABLED=true in .env
    auth_enabled: bool = False

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        (p / "sessions").mkdir(exist_ok=True)
        (p / "cloned_sites").mkdir(exist_ok=True)
        (p / "reports").mkdir(exist_ok=True)
        (p / "screenshots").mkdir(exist_ok=True)
        return p


settings = Settings()
