"""Anthropic Claude provider."""
from __future__ import annotations
import base64, json, re
from typing import Any
import httpx

from .base import ToolCall, ToolCallResponse

_BASE = "https://api.anthropic.com/v1"
_TEXT_MODEL = "claude-haiku-4-5-20251001"
_VISION_MODEL = "claude-sonnet-4-6"


def _safe_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group()) if m else {}


class AnthropicProvider:
    supports_tools = True

    def __init__(self, api_key: str, text_model: str = _TEXT_MODEL, vision_model: str = _VISION_MODEL):
        self._api_key = api_key
        self._text_model = text_model
        self._vision_model = vision_model
        self._embed_model = "unsupported"
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{_BASE}{path}", headers=self._headers, json=payload)
            r.raise_for_status()
        return r.json()

    async def chat(self, messages: list[dict], *, json_mode: bool = False, **kwargs) -> str:
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)
        payload: dict = {
            "model": self._text_model,
            "max_tokens": 4096,
            "messages": user_msgs,
        }
        if system_msg:
            payload["system"] = system_msg
        data = await self._post("/messages", payload)
        return data["content"][0]["text"]

    async def chat_json(self, system: str, user: str, **kwargs) -> dict:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = await self.chat(msgs)
        return _safe_json(text)

    async def vision(self, prompt: str, image_bytes: bytes, **kwargs) -> str:
        b64 = base64.b64encode(image_bytes).decode()
        msgs = [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": prompt},
        ]}]
        payload = {"model": self._vision_model, "max_tokens": 4096, "messages": msgs}
        data = await self._post("/messages", payload)
        return data["content"][0]["text"]

    async def vision_json(self, prompt: str, image_bytes: bytes, **kwargs) -> dict:
        text = await self.vision(prompt + "\nRespond with valid JSON only.", image_bytes)
        return _safe_json(text)

    async def embed(self, text: str) -> list[float]:
        # Anthropic does not have an embedding API; raise to trigger fallback
        raise NotImplementedError("Anthropic does not support embeddings — use Mistral or OpenAI")

    async def close(self) -> None:
        pass

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> ToolCallResponse:
        """Anthropic Messages API with native function-calling.

        Translates the unified tool schema `{name, description, input_schema}`
        into Anthropic's expected shape (same field names — they happen to
        match) and converts the response back into a `ToolCallResponse`.
        """
        system_msg = ""
        user_msgs: list[dict] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        payload: dict = {
            "model": self._text_model,
            "max_tokens": max_tokens,
            "messages": user_msgs,
            "tools": tools,
        }
        if system_msg:
            payload["system"] = system_msg

        data = await self._post("/messages", payload)

        # Anthropic returns a `content` list of blocks. Text blocks have
        # `type=text`; tool_use blocks have `type=tool_use` with name +
        # input + id. We collect both.
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content", []):
            btype = block.get("type")
            if btype == "text":
                text_parts.append(str(block.get("text", "")))
            elif btype == "tool_use":
                tool_calls.append(ToolCall(
                    id=str(block.get("id") or ""),
                    name=str(block.get("name") or ""),
                    arguments=dict(block.get("input") or {}),
                ))

        return ToolCallResponse(
            text="\n".join(text_parts).strip(),
            tool_calls=tool_calls,
            finish_reason=str(data.get("stop_reason") or ""),
        )
