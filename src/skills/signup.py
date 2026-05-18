"""Skill: create an account on an arbitrary site using a disposable mailbox."""

from __future__ import annotations

import asyncio
import random
import re
import string
from dataclasses import dataclass

from ..core.agent import Agent, TaskResult
from ..utils.logger import log
from ..utils.temp_mail import TempInbox, TempMailClient


@dataclass
class SignupResult:
    email: str
    password: str
    site_url: str
    verification_link: str | None
    agent_result: TaskResult


def _strong_password() -> str:
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%&*?"]
    base = [random.choice(p) for p in pools]
    base += random.choices(string.ascii_letters + string.digits, k=12)
    random.shuffle(base)
    return "".join(base)


async def signup(
    site_url: str,
    *,
    full_name: str | None = None,
    extra_instructions: str = "",
) -> SignupResult:
    mail = TempMailClient()
    inbox: TempInbox = await mail.create_inbox()
    password = _strong_password()
    name = full_name or f"User{random.randint(1000,9999)}"

    goal = (
        f"Open {site_url} and create a new account using:\n"
        f"  email: {inbox.email}\n"
        f"  password: {password}\n"
        f"  full name: {name}\n"
        "Click the registration / sign-up button, fill every required field, "
        "accept terms, and submit. If the site requires email verification, "
        "stop after submitting and respond with done.\n"
        f"{extra_instructions}"
    )

    async with Agent() as agent:
        result = await agent.run(goal)

    verification_link: str | None = None
    try:
        msg = await mail.wait_for_message(inbox, timeout_s=120)
        body = (msg.get("text") or "") + " " + " ".join(msg.get("html") or [])
        m = re.search(r"https?://[^\s\"<>]+", body)
        verification_link = m.group(0) if m else None
        if verification_link:
            log.info(f"🔗 verification link: {verification_link}")
    except TimeoutError:
        log.warning("No verification email arrived within timeout")
    finally:
        await mail.close()

    if verification_link:
        async with Agent() as agent2:
            await agent2.run(
                f"Open this verification URL exactly and confirm the new account is "
                f"verified: {verification_link}"
            )

    return SignupResult(
        email=inbox.email,
        password=password,
        site_url=site_url,
        verification_link=verification_link,
        agent_result=result,
    )
