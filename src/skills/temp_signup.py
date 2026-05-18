"""Skill: sign up to a site with a temp-mail address and PERSIST the session.

Builds on top of `skills.signup` (the disposable-mailbox flow) but:
  1. Runs the signup inside a persistent browser profile under
     `outputs/profiles/<slug>/` so cookies / localStorage survive.
  2. After verification, records the credentials in the existing memory
     store so the `login` skill can recall them later.
  3. Writes a JSON ledger card to
     `outputs/accounts/<slug>.json` — the operator can list/audit all
     accounts the agent has created, without grepping browser profiles.

Why this is a separate skill and not a flag on `signup`:
  - The old `signup()` flow intentionally uses a throwaway browser
    context so each run is hermetic. Changing its default would break
    existing automations that rely on fresh contexts.
  - Operators who specifically WANT the account to persist (so they
    can come back tomorrow without re-running login) get a dedicated
    skill with explicit intent.

Public surface:
    result = await temp_signup_persist(
        site_url,
        profile_name="my-account",   # optional; defaults to slug of host
        full_name="Mohamed Ahmed",
        extra_instructions="...",
    )
    # → result.session_dir is a persistent profile path
    # → result.account_card is a json file path with credentials + audit
"""
from __future__ import annotations

import json
import random
import re
import string
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..core.agent import Agent, TaskResult
from ..utils.logger import log
from ..utils.temp_mail import TempInbox, TempMailClient


@dataclass
class PersistentSignupResult:
    email: str
    password: str
    site_url: str
    profile_name: str
    session_dir: str          # persistent browser profile path
    account_card: str         # path to the JSON ledger entry
    verification_link: str | None
    verified: bool
    agent_result: dict


def _strong_password(length: int = 16) -> str:
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%&*?"]
    base = [random.choice(p) for p in pools]
    base += random.choices(string.ascii_letters + string.digits, k=max(0, length - len(base)))
    random.shuffle(base)
    return "".join(base)


def _slug_for(site_url: str) -> str:
    """Stable filesystem slug for `outputs/profiles/<slug>/`."""
    host = (urlparse(site_url).hostname or "site").lower()
    return re.sub(r"[^a-z0-9]+", "_", host).strip("_") or "site"


async def temp_signup_persist(
    site_url: str,
    *,
    profile_name: str | None = None,
    full_name: str | None = None,
    extra_instructions: str = "",
    verification_timeout_s: int = 120,
    headless: bool | None = None,
) -> PersistentSignupResult:
    """Sign up + persist the session permanently + remember the credentials.

    The browser profile (`outputs/profiles/<slug>/`) survives across
    runs. Login on subsequent days just needs `python run.py login
    <site_url> <email> <password>` and that profile auto-recovers.
    """
    slug = profile_name or _slug_for(site_url)

    # Persistent browser profile — same dir the `login` skill uses,
    # so the two are perfectly compatible.
    session_dir = settings.output_path / "profiles" / slug
    session_dir.mkdir(parents=True, exist_ok=True)

    # Disposable email — but the inbox stays open long enough to
    # grab the verification link before we close it.
    mail = TempMailClient()
    inbox: TempInbox = await mail.create_inbox()
    password = _strong_password()
    name = full_name or f"User{random.randint(10000, 99999)}"

    goal = (
        f"Open {site_url} and create a new account using these credentials:\n"
        f"  email:     {inbox.email}\n"
        f"  password:  {password}\n"
        f"  full name: {name}\n\n"
        "Steps to follow:\n"
        "  1. Click the registration / sign-up button (search the page if needed).\n"
        "  2. Fill EVERY required field — name, email, password, password-confirm.\n"
        "  3. Accept the terms-of-service checkbox if present.\n"
        "  4. Submit the form.\n"
        "  5. If the site requires email verification, STOP here and emit 'done'.\n"
        "     The verification link will be opened in a second pass.\n"
        "If the site refuses temp-mail addresses, emit 'fail' with a clear reason.\n"
        f"{extra_instructions}"
    )

    # The persistent profile here means the cookies the site sets
    # during signup (CSRF, anti-bot, MUID, session) are kept on disk
    # and reused on every subsequent login.
    async with Agent(headless=headless, user_data_dir=session_dir) as agent:
        result: TaskResult = await agent.run(goal)

    # ── Verification link harvest ─────────────────────────────────
    verification_link: str | None = None
    verified = False
    try:
        msg = await mail.wait_for_message(inbox, timeout_s=verification_timeout_s)
        body = (msg.get("text") or "") + " " + " ".join(msg.get("html") or [])
        m = re.search(r"https?://[^\s\"<>]+", body)
        verification_link = m.group(0) if m else None
        if verification_link:
            log.info(f"🔗 verification link: {verification_link}")
    except TimeoutError:
        log.warning("No verification email arrived within the timeout — account may still work without it.")
    finally:
        await mail.close()

    if verification_link:
        try:
            # SAME profile dir → the verification click lands in the
            # same session the site just initialised. Sites that gate
            # behind cookies-set-at-signup work correctly here.
            async with Agent(headless=headless, user_data_dir=session_dir) as agent2:
                v_result = await agent2.run(
                    f"Open this verification URL and confirm the new account "
                    f"is now verified / logged in: {verification_link}"
                )
                verified = bool(v_result.success)
        except Exception as exc:  # noqa: BLE001
            log.warning(f"Verification step failed: {exc}")

    # ── Remember credentials for future `login` runs ───────────────
    try:
        from ..memory import get_memory
        mem = await get_memory()
        await mem.remember_login(site_url, str(session_dir), inbox.email)
        log.info(f"Memory: saved login mapping for {site_url} ({inbox.email})")
    except Exception as exc:
        log.debug(f"Memory remember_login skipped: {exc}")

    # ── Write the audit ledger card ────────────────────────────────
    accounts_dir = settings.output_path / "accounts"
    accounts_dir.mkdir(parents=True, exist_ok=True)
    card_path = accounts_dir / f"{slug}.json"
    card = {
        "site_url": site_url,
        "email": inbox.email,
        "password": password,           # operator-visible; the agent is on the operator's host
        "full_name": name,
        "profile_name": slug,
        "session_dir": str(session_dir),
        "verification_link": verification_link,
        "verified": verified,
        "agent_task_id": result.task_id,
        "agent_success": result.success,
        "created_at": time.time(),
    }
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"📇 Account card written: {card_path}")

    return PersistentSignupResult(
        email=inbox.email,
        password=password,
        site_url=site_url,
        profile_name=slug,
        session_dir=str(session_dir),
        account_card=str(card_path),
        verification_link=verification_link,
        verified=verified,
        agent_result=result.to_dict(),
    )


def list_accounts() -> list[dict]:
    """Read every account card the agent has created. Used by CLI/UI to
    render an audit table without exposing browser profile internals."""
    d = settings.output_path / "accounts"
    if not d.exists():
        return []
    out: list[dict] = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def forget_account(profile_name: str) -> bool:
    """Delete the audit card AND the persistent browser profile dir for
    a given account. Returns True if at least one of them existed."""
    found = False
    card = settings.output_path / "accounts" / f"{profile_name}.json"
    if card.exists():
        card.unlink()
        found = True
    profile = settings.output_path / "profiles" / profile_name
    if profile.exists():
        import shutil
        shutil.rmtree(profile, ignore_errors=True)
        found = True
    return found
