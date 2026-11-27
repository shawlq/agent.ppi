"""Runtime action executor: serial queue with replace semantics."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Protocol

from .context import RuntimeContext

logger = logging.getLogger(__name__)


class ActionClient(Protocol):
    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class ActionExecutor:
    """
    Manage 3–5 step sequences after LLM.

    - replace(): clear pending (not yet started); keep current running item;
      enqueue the new sequence.
    - Interval matches console ActionQueue: await client.run_action which
      already blocks for cost_time_sec.
    """

    def __init__(self, client: ActionClient, context: RuntimeContext) -> None:
        self.client = client
        self.context = context
        self._pending: deque[dict[str, Any]] = deque()
        self._running: dict[str, Any] | None = None
        self._lock = asyncio.Lock()
        self._pump_task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._closed = False

    def start(self) -> None:
        if self._pump_task is None or self._pump_task.done():
            self._closed = False
            self._pump_task = asyncio.create_task(self._pump(), name="action-executor")

    async def close(self) -> None:
        self._closed = True
        self._wake.set()
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
            self._pump_task = None
        async with self._lock:
            self._pending.clear()
            self._running = None

    async def replace(self, sequence: list[dict[str, Any]]) -> None:
        """sequence items: {action_def, params}."""
        async with self._lock:
            cleared = len(self._pending)
            self._pending.clear()
            for item in sequence:
                self._pending.append(
                    {
                        "action_def": item["action_def"],
                        "params": dict(item.get("params") or {}),
                    }
                )
            logger.info(
                "executor replace: cleared_pending=%d new=%d running=%s",
                cleared,
                len(sequence),
                (self._running or {}).get("action_def", {}).get("function"),
            )
        self._wake.set()
        self.start()

    def pending_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "function": x["action_def"].get("function"),
                "params": x["params"],
            }
            for x in list(self._pending)
        ]

    async def _pump(self) -> None:
        while not self._closed:
            item = await self._pop_next()
            if item is None:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                continue

            action_def = item["action_def"]
            params = item["params"]
            fn = action_def.get("function")
            self.context.record_sent(action_def, params)
            logger.info("executor run_action start function=%s", fn)
            try:
                result = await self.client.run_action(action_def, params)
                logger.info(
                    "executor run_action done function=%s ok=%s",
                    fn,
                    (result or {}).get("ok", True),
                )
            except Exception:
                logger.exception("executor run_action failed function=%s", fn)
            finally:
                async with self._lock:
                    self._running = None

    async def _pop_next(self) -> dict[str, Any] | None:
        async with self._lock:
            if self._running is not None:
                return None
            if not self._pending:
                return None
            item = self._pending.popleft()
            self._running = item
            return item
