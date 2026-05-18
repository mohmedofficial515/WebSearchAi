"""Search backends — API-first so the agent doesn't fight CAPTCHAs.

Public surface:
    await search(query, max_results=...) -> list[SearchResult]

The dispatcher picks the best available backend at call time:
    1. Tavily (if TAVILY_API_KEY is set) — purpose-built for AI agents
    2. DDGS (DuckDuckGo HTML JSON) — no key required, works most of the time
    3. raise — caller can fall back to scraping a search engine in the browser
"""

from .backends import SearchResult, search

__all__ = ["SearchResult", "search"]
