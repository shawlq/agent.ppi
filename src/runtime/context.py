"""Runtime context: identity, allowed actions, sent-action history."""

from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any


class RuntimeContext:
    def __init__(
        self,
        *,
        proxy: dict[str, Any],
        identity_text: str,
        history_maxlen: int = 20,
    ) -> None:
        self.proxy = proxy
        self.identity_text = identity_text.strip()
        self.allowed_actions: list[dict[str, Any]] = list(proxy.get("actions") or [])
        self._history: deque[dict[str, Any]] = deque(maxlen=max(1, history_maxlen))

    @classmethod
    def from_files(
        cls,
        proxy: dict[str, Any],
        identity_path: str | Path,
        history_maxlen: int = 20,
    ) -> RuntimeContext:
        text = Path(identity_path).read_text(encoding="utf-8")
        return cls(proxy=proxy, identity_text=text, history_maxlen=history_maxlen)

    def record_sent(self, action_def: dict[str, Any], params: dict[str, Any] | None = None) -> None:
        """Record an action that has started being sent to the agent client."""
        self._history.append(
            {
                "function": action_def.get("function"),
                "action": action_def.get("action"),
                "params": dict(params or {}),
                "stamp": time.time(),
            }
        )

    def history(self) -> list[dict[str, Any]]:
        return list(self._history)

    def allowed_actions_brief(self) -> list[dict[str, Any]]:
        brief: list[dict[str, Any]] = []
        for a in self.allowed_actions:
            item: dict[str, Any] = {
                "function": a.get("function"),
                "action": a.get("action"),
                "cost_time_sec": a.get("cost_time_sec"),
                "kind": a.get("kind"),
            }
            params = a.get("params") or []
            if params:
                item["params"] = [
                    {
                        "name": p.get("name"),
                        "type": p.get("type"),
                        "default": p.get("default"),
                    }
                    for p in params
                ]
            brief.append(item)
        return brief

    def find_action(self, function: str) -> dict[str, Any] | None:
        for a in self.allowed_actions:
            if a.get("function") == function:
                return a
        return None

    def to_prompt_sections(self) -> dict[str, str]:
        history = self.history()
        if history:
            history_text = json.dumps(history, ensure_ascii=False, indent=2)
        else:
            history_text = "（暂无）"
        return {
            "identity": self.identity_text,
            "history": history_text,
            "allowed_actions": json.dumps(
                self.allowed_actions_brief(), ensure_ascii=False, indent=2
            ),
        }
