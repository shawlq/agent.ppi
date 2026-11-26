"""VLM / LLM abstract protocols."""

from __future__ import annotations

from typing import Any, Protocol


class VLMClient(Protocol):
    async def describe(
        self, *, image_bytes: bytes | None, image_path: str | None, instruction: str
    ) -> str: ...


class LLMClient(Protocol):
    async def complete(self, prompt: str) -> str: ...
