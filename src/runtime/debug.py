"""Debug hub: callbacks + self-describing panel snapshots for UI."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DebugCallback = Callable[[dict[str, Any]], None]

IMAGE_SRC_PREFIX = "/api/debug/image"


def _panel_text(value: str) -> dict[str, Any]:
    return {"type": "text", "value": value}


def _panel_json(value: Any) -> dict[str, Any]:
    return {"type": "json", "value": value}


def _panel_image(name: str, rev: int) -> dict[str, Any]:
    return {
        "type": "image",
        "rev": rev,
        "src": f"{IMAGE_SRC_PREFIX}/{name}",
    }


class DebugHub:
    """Thread-safe debug event hub used by ThinkLoop and HTTP/SSE adapters.

    Emits envelopes: ``{kind, stamp, round_id?, panels:{name: {type, ...}}}``.
    Panel types are ``text`` | ``json`` | ``image``. UI renders by type only.
    """

    def __init__(self, *, history_rounds: int = 3) -> None:
        self._lock = threading.Lock()
        self._callbacks: list[DebugCallback] = []
        self._latest: dict[str, Any] | None = None
        self._images: dict[str, bytes] = {}
        self._revs: dict[str, int] = {}
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
            return self._revs.get("cam", 0)

    @property
    def df_rev(self) -> int:
        with self._lock:
            return self._revs.get("df", 0)

    def _set_image_locked(self, name: str, jpeg: bytes) -> int:
        self._images[name] = jpeg
        rev = self._revs.get(name, 0) + 1
        self._revs[name] = rev
        return rev

    def update_cam(self, jpeg: bytes | None, *, emit: bool = True) -> int:
        if not jpeg:
            return self.cam_rev
        with self._lock:
            rev = self._set_image_locked("cam", jpeg)
            panel = _panel_image("cam", rev)
            snap = {
                "kind": "cam",
                "stamp": time.time(),
                "panels": {"cam": panel},
            }
            if self._latest:
                merged = dict(self._latest)
                prev_panels = dict(merged.get("panels") or {})
                prev_panels["cam"] = panel
                merged["kind"] = "cam"
                merged["stamp"] = snap["stamp"]
                merged["panels"] = prev_panels
                self._latest = merged
            else:
                self._latest = {
                    "kind": "cam",
                    "stamp": snap["stamp"],
                    "panels": {"cam": panel},
                }
            cbs = list(self._callbacks)
        if emit:
            for cb in cbs:
                try:
                    cb(snap)
                except Exception:
                    logger.exception("debug cam callback failed")
        return rev

    def get_image(self, name: str) -> bytes | None:
        with self._lock:
            return self._images.get(name)

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._latest:
                return None
            out = dict(self._latest)
            panels = out.get("panels")
            if isinstance(panels, dict):
                out["panels"] = dict(panels)
            return out

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
            df_rev = self._revs.get("df", 0)
            if df_jpeg:
                df_rev = self._set_image_locked("df", df_jpeg)
            cam_rev = self._revs.get("cam", 0)

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

            vlm_value: Any = vlm_parsed if vlm_parsed is not None else vlm_raw
            panels: dict[str, Any] = {}
            if cam_rev > 0:
                panels["cam"] = _panel_image("cam", cam_rev)
            if df_rev > 0:
                panels["df"] = _panel_image("df", df_rev)
            panels["vlm"] = (
                _panel_json(vlm_value)
                if not isinstance(vlm_value, str)
                else _panel_text(vlm_value)
            )
            panels["context"] = _panel_json(context)
            panels["prompt"] = _panel_text(prompt)
            panels["llm"] = _panel_text(llm_raw)
            panels["reason"] = _panel_text(reason_text)
            panels["actions_valid"] = _panel_json(actions_brief)
            panels["actions_history"] = _panel_json(list(self._actions_history))
            panels["errors"] = _panel_json(list(errors))

            snap = {
                "kind": "round",
                "stamp": time.time(),
                "round_id": round_id,
                "panels": panels,
            }
            self._latest = snap
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(snap)
            except Exception:
                logger.exception("debug round callback failed")
        return snap
