"""sim_agent client — ROS-shaped commands over local sim HTTP gateway."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MessageCallback = Callable[[str, dict[str, Any]], None]

# Tiny placeholder JPEG bytes for mock subscribe (content need not decode).
_PLACEHOLDER_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


class SimAgentClient:
    """Publish /sim_dog/command to the local sim server (no system rosbridge)."""

    def __init__(self, proxy: dict[str, Any]) -> None:
        self.proxy = proxy
        self.host = str(proxy.get("ip") or "127.0.0.1")
        self.port = int(proxy.get("sim_http_port", 8765))
        topics = proxy.get("topics") or {}
        self.command_topic = topics.get("command", "/sim_dog/command")
        self.image_topic = topics.get("image", "/sim_dog/image_raw")
        self._ok = False
        self._callbacks: dict[str, MessageCallback] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def update_host(self, host: str) -> None:
        self.host = host.strip()
        self.proxy["ip"] = self.host

    def _snapshot_url(self) -> str:
        return f"{self.base_url}/snapshot?topic={self.image_topic}"

    async def connect(self) -> None:
        health = await self.health()
        if not health.get("ok"):
            raise ConnectionError(
                f"sim gateway unreachable: {self.base_url}/api/health"
            )
        self._ok = True
        logger.info("sim_agent connected %s", self.base_url)

    async def close(self) -> None:
        for modality in list(self._tasks):
            await self.unsubscribe_message(modality)
        self._ok = False

    async def health(self) -> dict[str, Any]:
        url = f"{self.base_url}/api/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                r = await http.get(url)
                data = r.json() if r.status_code == 200 else {}
                ok = r.status_code == 200 and bool(data.get("ok", True))
                self._ok = ok
                return {
                    "mode": "sim",
                    "agent": "sim_agent",
                    "ok": ok,
                    "url": url,
                    "image_ok": bool(data.get("image_ok")),
                    "image_topic": data.get("image_topic"),
                    "sim": data,
                }
        except Exception as e:
            self._ok = False
            return {
                "mode": "sim",
                "agent": "sim_agent",
                "ok": False,
                "url": url,
                "image_ok": False,
                "error": str(e),
            }

    def _merge_params(
        self, action_def: dict[str, Any], params: dict[str, Any] | None
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for p in action_def.get("params") or []:
            name = p.get("name")
            if name and "default" in p:
                merged[name] = p["default"]
        if params:
            merged.update(params)
        return merged

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        fn = action_def.get("function")
        if not fn:
            raise ValueError("action missing function")
        cost = float(action_def.get("cost_time_sec") or 1.0)
        payload = {
            "function": fn,
            "params": self._merge_params(action_def, params),
            "cost_time_sec": cost,
        }
        body = {
            "topic": self.command_topic,
            "data": payload,
        }
        url = f"{self.base_url}/api/ros/command"
        async with httpx.AsyncClient(timeout=10.0) as http:
            r = await http.post(url, json=body)
            if r.status_code >= 400:
                detail = r.text
                try:
                    detail = r.json().get("detail", detail)
                except Exception:
                    pass
                raise RuntimeError(f"sim command failed: {detail}")
            result = r.json() if r.content else {"ok": True}

        # Align queue timing with action cost (sim renders in parallel via WS).
        await asyncio.sleep(min(cost, 30.0))
        return {
            "ok": True,
            "mode": "sim",
            "agent": "sim_agent",
            "kind": action_def.get("kind", "sim_command"),
            "function": fn,
            "topic": self.command_topic,
            "duration_sec": cost,
            "sim": result,
        }

    async def _poll_image_loop(
        self, callback: MessageCallback, poll_hz: float
    ) -> None:
        period = 1.0 / max(poll_hz, 0.1)
        url = self._snapshot_url()
        logger.info("sim image poll start url=%s hz=%.2f", url, poll_hz)
        while True:
            try:
                async with httpx.AsyncClient(timeout=2.0) as http:
                    r = await http.get(url)
                    if r.status_code == 200 and r.content:
                        callback(
                            "image",
                            {
                                "modality": "image",
                                "stamp": time.time(),
                                "encoding": "jpeg",
                                "data": bytes(r.content),
                                "topic": self.image_topic,
                            },
                        )
                    else:
                        logger.debug("sim snapshot status=%s", r.status_code)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("sim snapshot poll error: %s", e)
            await asyncio.sleep(period)

    async def subscribe_message(
        self,
        modality: str,
        callback: MessageCallback,
        *,
        poll_hz: float = 2.0,
    ) -> None:
        modality = modality.strip()
        await self.unsubscribe_message(modality)
        self._callbacks[modality] = callback
        if modality == "image":
            self._tasks[modality] = asyncio.create_task(
                self._poll_image_loop(callback, poll_hz),
                name=f"sim-sub-{modality}",
            )
        else:
            raise ValueError(f"unsupported modality={modality!r}")

    async def unsubscribe_message(self, modality: str) -> None:
        self._callbacks.pop(modality, None)
        task = self._tasks.pop(modality, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


class SimMockClient:
    """Offline mock for runtime smoke without sim HTTP gateway."""

    def __init__(self, proxy: dict[str, Any] | None = None) -> None:
        self.proxy = proxy or {}
        topics = self.proxy.get("topics") or {}
        self.image_topic = topics.get("image", "/sim_dog/image_raw")
        self._ok = True
        self._callbacks: dict[str, MessageCallback] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def connect(self) -> None:
        self._ok = True
        logger.info("sim MockClient ready")

    async def close(self) -> None:
        for modality in list(self._tasks):
            await self.unsubscribe_message(modality)
        self._ok = False

    async def health(self) -> dict[str, Any]:
        return {
            "mode": "mock",
            "agent": "sim_agent",
            "ok": True,
            "image_ok": True,
        }

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cost = float(action_def.get("cost_time_sec") or 1.0)
        await asyncio.sleep(min(cost, 0.2))
        return {
            "ok": True,
            "mode": "mock",
            "agent": "sim_agent",
            "function": action_def.get("function"),
            "params": params or {},
            "duration_sec": cost,
        }

    async def _mock_image_loop(
        self, callback: MessageCallback, poll_hz: float
    ) -> None:
        period = 1.0 / max(poll_hz, 0.1)
        while True:
            callback(
                "image",
                {
                    "modality": "image",
                    "stamp": time.time(),
                    "encoding": "jpeg",
                    "data": _PLACEHOLDER_JPEG,
                    "topic": self.image_topic,
                },
            )
            await asyncio.sleep(period)

    async def subscribe_message(
        self,
        modality: str,
        callback: MessageCallback,
        *,
        poll_hz: float = 2.0,
    ) -> None:
        modality = modality.strip()
        await self.unsubscribe_message(modality)
        self._callbacks[modality] = callback
        if modality == "image":
            self._tasks[modality] = asyncio.create_task(
                self._mock_image_loop(callback, poll_hz),
                name="sim-mock-image",
            )
        else:
            raise ValueError(f"unsupported modality={modality!r}")

    async def unsubscribe_message(self, modality: str) -> None:
        self._callbacks.pop(modality, None)
        task = self._tasks.pop(modality, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def create_client(
    proxy: dict[str, Any], mode: str = "sim"
) -> SimAgentClient | SimMockClient:
    mode = (mode or "sim").strip().lower()
    if mode == "mock":
        return SimMockClient(proxy)
    return SimAgentClient(proxy)
