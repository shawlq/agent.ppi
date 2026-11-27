"""Executor replace clears pending while keeping running item."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from src.runtime.context import RuntimeContext
from src.runtime.executor import ActionExecutor


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.gate = asyncio.Event()
        self.started = asyncio.Event()

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        fn = str(action_def.get("function"))
        self.calls.append(fn)
        self.started.set()
        await self.gate.wait()
        return {"ok": True, "function": fn}


class ExecutorReplaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_replace_clears_pending(self) -> None:
        proxy = {
            "actions": [
                {"function": "a", "action": "A", "cost_time_sec": 0.1},
                {"function": "b", "action": "B", "cost_time_sec": 0.1},
                {"function": "c", "action": "C", "cost_time_sec": 0.1},
                {"function": "d", "action": "D", "cost_time_sec": 0.1},
            ]
        }
        ctx = RuntimeContext(proxy=proxy, identity_text="id", history_maxlen=10)
        client = FakeClient()
        ex = ActionExecutor(client, ctx)
        ex.start()

        def item(fn: str) -> dict[str, Any]:
            return {"action_def": {"function": fn}, "params": {}}

        await ex.replace([item("a"), item("b"), item("c")])
        await asyncio.wait_for(client.started.wait(), timeout=2.0)
        # a is running; b,c pending → replace with d only
        await ex.replace([item("d")])
        self.assertEqual(ex.pending_snapshot()[0]["function"], "d")
        client.gate.set()
        await asyncio.sleep(0.15)
        self.assertIn("a", client.calls)
        self.assertIn("d", client.calls)
        self.assertNotIn("b", client.calls)
        self.assertNotIn("c", client.calls)
        await ex.close()


if __name__ == "__main__":
    unittest.main()
