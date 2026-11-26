"""Deterministic mock VLM / LLM for offline loop smoke tests."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_MOCK_ENV = {
    "summary": "室内平坦地面，前方约1米处疑似有人站立",
    "objects": [{"name": "person", "where": "front", "dist_m": 1.0}],
    "terrain": "indoor_flat",
    "affordances": ["greet", "observe", "approach"],
    "raw": "mock vision",
}

_MOCK_ACTIONS = [
    {"function": "stand", "params": {}},
    {"function": "sit", "params": {}},
    {"function": "nod", "params": {}},
]


class MockVLM:
    async def describe(
        self, *, image_bytes: bytes | None, image_path: str | None, instruction: str
    ) -> str:
        _ = (image_bytes, image_path, instruction)
        return json.dumps(_MOCK_ENV, ensure_ascii=False)


class MockLLM:
    def __init__(self, preferred_functions: list[str] | None = None) -> None:
        self.preferred_functions = preferred_functions or []

    async def complete(self, prompt: str) -> str:
        _ = prompt
        candidates = ["stand", "sit", "nod", "bow", "forward"]
        chosen = [
            fn
            for fn in candidates
            if f'"function": "{fn}"' in prompt or f'"{fn}"' in prompt
        ]
        if len(chosen) >= 3:
            actions = [{"function": fn, "params": {}} for fn in chosen[:3]]
        else:
            actions = list(_MOCK_ACTIONS)
        return json.dumps(
            {"reason": "mock: 按白名单挑前几个动作", "actions": actions},
            ensure_ascii=False,
        )
