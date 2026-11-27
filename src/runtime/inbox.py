"""Message inbox: client callbacks write here; pipeline reads latest snapshot."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MessageInbox:
    """Thread-safe latest-message cache. Image modality keeps only the newest frame."""

    def __init__(self, frame_path: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._latest: dict[str, dict[str, Any]] = {}
        self._frame_path = Path(frame_path) if frame_path else None
        if self._frame_path is not None:
            self._frame_path.parent.mkdir(parents=True, exist_ok=True)

    def on_message(self, modality: str, msg: dict[str, Any]) -> None:
        """Client callback entry. Signature: callback(modality, msg)."""
        modality = (modality or msg.get("modality") or "").strip()
        if not modality:
            logger.warning("inbox ignore message without modality")
            return

        stamp = msg.get("stamp", time.time())
        entry = dict(msg)
        entry["modality"] = modality
        entry["stamp"] = stamp

        if modality == "image":
            data = entry.get("data")
            if isinstance(data, (bytes, bytearray)) and self._frame_path is not None:
                try:
                    self._atomic_write(self._frame_path, bytes(data))
                    entry["path"] = str(self._frame_path)
                except OSError as e:
                    logger.warning("failed to save frame: %s", e)
            elif self._frame_path is not None and self._frame_path.is_file():
                entry.setdefault("path", str(self._frame_path))

        with self._lock:
            self._latest[modality] = entry

    def get(self, modality: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._latest.get(modality)
            return dict(item) if item else None

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {k: dict(v) for k, v in self._latest.items()}

    def has_image(self) -> bool:
        img = self.get("image")
        if not img:
            return False
        if img.get("data") or img.get("path"):
            return True
        return False

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
