"""Quick test of all configured LLM providers."""
import asyncio
import sys

sys.path.insert(0, ".")


async def main():
    from src.config import settings

    print(f"LLM_PROVIDER       : {settings.llm_provider}")
    print(f"OLLAMA_URL         : {settings.ollama_base_url}")
    print(f"OLLAMA_TEXT_MODEL  : {settings.ollama_text_model}")
    print(f"GROQ_KEY real      : {bool(settings.groq_api_key and '...' not in settings.groq_api_key)}")
    print(f"MISTRAL_KEY real   : {bool(settings.mistral_api_key and '...' not in settings.mistral_api_key)}")
    print(f"OPENROUTER_KEY real: {bool(settings.openrouter_api_key and '...' not in settings.openrouter_api_key)}")
    print(f"COHERE_KEY real    : {bool(settings.cohere_api_key and '...' not in settings.cohere_api_key)}")
    print()

    results = {}

    # ── Ollama ──────────────────────────────────────────────────────────────
    print("=== Ollama ===")
    try:
        from src.llm.providers.ollama import OllamaProvider
        p = OllamaProvider(
            base_url=settings.ollama_base_url,
            text_model=settings.ollama_text_model,
        )
        r = await asyncio.wait_for(
            p.chat([{"role": "user", "content": "Say hi in one word"}]),
            timeout=20,
        )
        print(f"  OK: {r[:80]}")
        results["ollama"] = "OK"
    except Exception as e:
        print(f"  FAIL: {e}")
        results["ollama"] = f"FAIL: {e}"

    # ── Cohere ──────────────────────────────────────────────────────────────
    print()
    print("=== Cohere ===")
    if settings.cohere_api_key:
        try:
            from src.llm.providers.cohere import CohereProvider
            p = CohereProvider(
                api_key=settings.cohere_api_key,
                text_model=settings.cohere_text_model,
            )
            r = await asyncio.wait_for(
                p.chat([{"role": "user", "content": "Say hi in one word"}]),
                timeout=15,
            )
            print(f"  OK: {r[:80]}")
            results["cohere"] = "OK"
        except Exception as e:
            print(f"  FAIL: {e}")
            results["cohere"] = f"FAIL: {e}"
    else:
        print("  SKIP (no API key)")
        results["cohere"] = "SKIP"

    # ── Groq ────────────────────────────────────────────────────────────────
    print()
    print("=== Groq ===")
    if settings.groq_api_key and "..." not in settings.groq_api_key:
        try:
            from src.llm.providers.groq import GroqProvider
            p = GroqProvider(
                api_key=settings.groq_api_key,
                text_model=settings.groq_text_model,
            )
            r = await asyncio.wait_for(
                p.chat([{"role": "user", "content": "Say hi in one word"}]),
                timeout=10,
            )
            print(f"  OK: {r[:80]}")
            results["groq"] = "OK"
        except Exception as e:
            print(f"  FAIL: {e}")
            results["groq"] = f"FAIL: {e}"
    else:
        print("  SKIP (placeholder key)")
        results["groq"] = "SKIP"

    # ── Mistral ─────────────────────────────────────────────────────────────
    print()
    print("=== Mistral ===")
    if settings.mistral_api_key and "..." not in settings.mistral_api_key:
        try:
            from src.llm.providers.mistral import MistralProvider
            p = MistralProvider(
                api_key=settings.mistral_api_key,
                text_model=settings.mistral_text_model,
                vision_model=settings.mistral_vision_model,
            )
            r = await asyncio.wait_for(
                p.chat([{"role": "user", "content": "Say hi in one word"}]),
                timeout=10,
            )
            print(f"  OK: {r[:80]}")
            results["mistral"] = "OK"
        except Exception as e:
            print(f"  FAIL: {e}")
            results["mistral"] = f"FAIL: {e}"
    else:
        print("  SKIP (placeholder key)")
        results["mistral"] = "SKIP"

    # ── OpenRouter ──────────────────────────────────────────────────────────
    print()
    print("=== OpenRouter ===")
    if settings.openrouter_api_key and "..." not in settings.openrouter_api_key:
        try:
            from src.llm.providers.openrouter import OpenRouterProvider
            p = OpenRouterProvider(
                api_key=settings.openrouter_api_key,
                text_model=settings.openrouter_text_model,
            )
            r = await asyncio.wait_for(
                p.chat([{"role": "user", "content": "Say hi in one word"}]),
                timeout=15,
            )
            print(f"  OK: {r[:80]}")
            results["openrouter"] = "OK"
        except Exception as e:
            print(f"  FAIL: {e}")
            results["openrouter"] = f"FAIL: {e}"
    else:
        print("  SKIP (placeholder key)")
        results["openrouter"] = "SKIP"

    print()
    print("=" * 40)
    print("SUMMARY:")
    for name, status in results.items():
        icon = "✓" if status == "OK" else ("~" if status == "SKIP" else "✗")
        print(f"  {icon} {name:15s} {status}")


asyncio.run(main())
