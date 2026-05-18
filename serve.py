"""Quick server entrypoint: `python serve.py`"""

import asyncio
import sys

# Force UTF-8 on Windows stdout/stderr so emoji log messages don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# On Windows the default asyncio policy in 3.8+ is SelectorEventLoop,
# which raises NotImplementedError when patchright/Playwright calls
# `create_subprocess_exec` to launch Chrome. Switching to the Proactor
# policy fixes it for the whole process. No-op on macOS/Linux.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

from src.config import settings


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        # Force the asyncio loop implementation — uvicorn's "auto" picks
        # uvloop where available, but on Windows we MUST stay on the
        # asyncio policy we set above so subprocess support is preserved.
        loop="asyncio",
    )
