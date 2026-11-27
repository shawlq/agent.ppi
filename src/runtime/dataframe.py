"""Assemble a multimodal dataframe from the message inbox."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .inbox import MessageInbox


@dataclass
class DataFrame:
    """Current sensing snapshot. Extensible beyond image (e.g. audio later)."""

    stamp: float
    image_path: str | None = None
    image_bytes: bytes | None = None
    image_encoding: str = "jpeg"
    modalities: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_inbox(cls, inbox: MessageInbox) -> DataFrame | None:
        snap = inbox.snapshot()
        if not snap:
            return None
        img = snap.get("image")
        image_bytes = None
        image_path = None
        encoding = "jpeg"
        if img:
            raw = img.get("data")
            if isinstance(raw, (bytes, bytearray)):
                image_bytes = bytes(raw)
            path = img.get("path")
            if path:
                image_path = str(path)
                if image_bytes is None and Path(path).is_file():
                    image_bytes = Path(path).read_bytes()
            encoding = str(img.get("encoding") or "jpeg")
        stamp = float((img or next(iter(snap.values()))).get("stamp") or time.time())
        return cls(
            stamp=stamp,
            image_path=image_path,
            image_bytes=image_bytes,
            image_encoding=encoding,
            modalities=snap,
        )

    @property
    def has_image(self) -> bool:
        return bool(self.image_bytes) or (
            bool(self.image_path) and Path(self.image_path).is_file()
        )
