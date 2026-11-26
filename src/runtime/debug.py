"""Debug hub: callbacks + latest snapshot / JPEG frames for UI panels."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DebugCallback = Callable[[dict[str, Any]], None]


@dataclass
class DebugSnapshot:
    round_id: int = 0
    stamp: float = 0.0
    cam_rev: int = 0
    df_rev: int = 0
    vlm_raw: str = ""
    vlm_parsed: dict[str, Any] | None = None
    context: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    llm_raw: str = ""
    reason: str = ""
    actions_valid: list[dict[str, Any]] = field(default_factory=list)
    actions_history: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    kind: str = "round"  # "round" | "cam"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DebugHub:
    """Thread-safe debug event hub used by ThinkLoop and HTTP/SSE adapters."""

    def __init__(self, *, history_rounds: int = 3) -> None:
        self._lock = threading.Lock()
        self._callbacks: list[DebugCallback] = []
        self._latest: dict[str, Any] | None = None
        self._cam_jpeg: bytes | None = None
        self._df_jpeg: bytes | None = None
        self._cam_rev = 0
        self._df_rev = 0
        self._round_id = 0
        self._actions_history: deque[dict[str, Any]] = deque(maxlen=max(1, history_rounds))

    def register(self, callback: DebugCallback) -> None:
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister(self, callback: DebugCallback) -> None:
        with self._lock:
            self._callbacks = [c for c in self._callbacks if c is not callback]

    @property
    def cam_rev(self) -> int:
        with self._lock:
            return self._cam_rev

    @property
    def df_rev(self) -> int:
        with self._lock:
            return self._df_rev

    def update_cam(self, jpeg: bytes | None, *, emit: bool = True) -> int:
        if not jpeg:
            return self.cam_rev
        with self._lock:
            self._cam_jpeg = jpeg
            self._cam_rev += 1
            rev = self._cam_rev
            snap = {
                "kind": "cam",
                "stamp": time.time(),
                "cam_rev": rev,
                "df_rev": self._df_rev,
            }
            # Keep text fields from latest round if any.
            if self._latest:
                merged = dict(self._latest)
                merged.update(snap)
                self._latest = merged
            else:
                self._latest = snap
            cbs = list(self._callbacks)
        if emit:
            for cb in cbs:
                try:
                    cb(snap)
                except Exception:
                    logger.exception("debug cam callback failed")
        return rev

    def get_cam_jpeg(self) -> bytes | None:
        with self._lock:
            return self._cam_jpeg

    def get_df_jpeg(self) -> bytes | None:
        with self._lock:
            return self._df_jpeg

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._latest) if self._latest else None

    def emit_round(
        self,
        *,
        df_jpeg: bytes | None,
        vlm_raw: str,
        vlm_parsed: dict[str, Any] | None,
        context: dict[str, Any],
        prompt: str,
        llm_raw: str,
        actions_valid: list[dict[str, Any]],
        errors: list[str],
        reason: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._round_id += 1
            round_id = self._round_id
            if df_jpeg:
                self._df_jpeg = df_jpeg
                self._df_rev += 1
            actions_brief = [
                {
                    "function": a.get("action_def", {}).get("function")
                    if "action_def" in a
                    else a.get("function"),
                    "params": a.get("params") or {},
                }
                for a in actions_valid
            ]
            reason_text = (reason or "").strip()
            hist_entry = {
                "round_id": round_id,
                "stamp": time.time(),
                "reason": reason_text,
                "actions": actions_brief,
            }
            self._actions_history.appendleft(hist_entry)
            snap = DebugSnapshot(
                round_id=round_id,
                stamp=time.time(),
                cam_rev=self._cam_rev,
                df_rev=self._df_rev,
                vlm_raw=vlm_raw,
                vlm_parsed=vlm_parsed,
                context=context,
                prompt=prompt,
                llm_raw=llm_raw,
                reason=reason_text,
                actions_valid=actions_brief,
                actions_history=list(self._actions_history),
                errors=list(errors),
                kind="round",
            ).to_dict()
            self._latest = snap
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(snap)
            except Exception:
                logger.exception("debug round callback failed")
        return snap
