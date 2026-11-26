"""OpenAI-compatible HTTP clients for VLM and LLM."""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _data_url(image_bytes: bytes, encoding: str = "jpeg") -> str:
    mime = "image/jpeg" if encoding in ("jpeg", "jpg") else f"image/{encoding}"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _message_text(payload: dict[str, Any]) -> str:
    try:
        msg = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"unexpected chat response: {payload!r}") from e
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    # Qwen3 reasoning models may leave content empty when truncated.
    reasoning = msg.get("reasoning") or msg.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        logger.warning("model returned reasoning without content; using reasoning tail")
        return reasoning
    raise RuntimeError(f"empty model content: {payload!r}")


class OpenAICompatVLM:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        timeout_sec: float = 60.0,
        max_tokens: int = 2048,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.extra_body = dict(extra_body or {})

    async def describe(
        self, *, image_bytes: bytes | None, image_path: str | None, instruction: str
    ) -> str:
        data = image_bytes
        if data is None and image_path:
            data = Path(image_path).read_bytes()
        if not data:
            raise ValueError("VLM describe requires image bytes or path")

        content: list[dict[str, Any]] = [
            {"type": "text", "text": instruction},
            {
                "type": "image_url",
                "image_url": {"url": _data_url(data)},
            },
        ]
        return await self._chat([{"role": "user", "content": content}])

    async def _chat(self, messages: list[dict[str, Any]]) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.max_tokens,
        }
        body.update(self.extra_body)
        async with httpx.AsyncClient(timeout=self.timeout_sec) as http:
            r = await http.post(url, headers=headers, json=body)
            r.raise_for_status()
            payload = r.json()
        return _message_text(payload)


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "EMPTY",
        timeout_sec: float = 60.0,
        max_tokens: int = 2048,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.extra_body = dict(extra_body or {})

    async def complete(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": self.max_tokens,
        }
        body.update(self.extra_body)
        async with httpx.AsyncClient(timeout=self.timeout_sec) as http:
            r = await http.post(url, headers=headers, json=body)
            r.raise_for_status()
            payload = r.json()
        return _message_text(payload)
