"""Disposable email via mail.tm — fully free, no API key needed."""

from __future__ import annotations

import asyncio
import random
import string
from dataclasses import dataclass

import httpx

from .logger import log

MAIL_TM_BASE = "https://api.mail.tm"


@dataclass
class TempInbox:
    email: str
    password: str
    token: str


class TempMailClient:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=MAIL_TM_BASE, timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_domain(self) -> str:
        r = await self._client.get("/domains")
        r.raise_for_status()
        data = r.json()
        members = data.get("hydra:member") or data.get("member") or []
        if not members:
            raise RuntimeError("mail.tm: no domains available")
        return members[0]["domain"]

    async def create_inbox(self, prefix: str | None = None) -> TempInbox:
        domain = await self.get_domain()
        local = prefix or "".join(
            random.choices(string.ascii_lowercase + string.digits, k=12)
        )
        email = f"{local}@{domain}"
        password = "".join(
            random.choices(string.ascii_letters + string.digits, k=16)
        )
        r = await self._client.post(
            "/accounts", json={"address": email, "password": password}
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"mail.tm account creation failed: {r.text}")

        tr = await self._client.post(
            "/token", json={"address": email, "password": password}
        )
        tr.raise_for_status()
        token = tr.json()["token"]
        log.info(f"📧 temp inbox: {email}")
        return TempInbox(email=email, password=password, token=token)

    async def wait_for_message(
        self,
        inbox: TempInbox,
        timeout_s: int = 120,
        contains: str | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {inbox.token}"}
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            r = await self._client.get("/messages", headers=headers)
            if r.status_code == 200:
                items = r.json().get("hydra:member") or r.json().get("member") or []
                for msg in items:
                    msg_id = msg["id"]
                    detail = await self._client.get(
                        f"/messages/{msg_id}", headers=headers
                    )
                    if detail.status_code == 200:
                        full = detail.json()
                        body = full.get("text", "") + " " + full.get("html", [""])[0]
                        if contains is None or contains.lower() in body.lower():
                            return full
            await asyncio.sleep(3)
        raise TimeoutError("No verification email arrived in time")
