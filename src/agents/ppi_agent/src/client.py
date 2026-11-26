"""ppi_agent client — PuppyPi via rosbridge (or mock)."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# PuppyPi action-group file basename may differ from logical function name.
ACTION_GROUP_ALIASES: dict[str, str] = {
    "push_up": "push-up01",
}

MessageCallback = Callable[[str, dict[str, Any]], None]

# Tiny placeholder JPEG for mock image stream (need not decode).
_PLACEHOLDER_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


class AgentClient(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def subscribe_message(
        self,
        modality: str,
        callback: MessageCallback,
        *,
        poll_hz: float = 2.0,
    ) -> None: ...

    @abstractmethod
    async def unsubscribe_message(self, modality: str) -> None: ...


class _ImagePollMixin:
    """HTTP snapshot polling used by RosbridgeClient (web_video_server)."""

    proxy: dict[str, Any]
    host: str
    _callbacks: dict[str, MessageCallback]
    _tasks: dict[str, asyncio.Task[Any]]

    def _image_snapshot_url(self) -> str:
        topics = self.proxy.get("topics") or {}
        topic = topics.get("image", "/usb_cam/image_raw")
        port = int(self.proxy.get("web_video_port", 8080))
        host = str(self.proxy.get("ip") or self.host)
        return f"http://{host}:{port}/snapshot?topic={topic}"

    async def _poll_image_loop(
        self, callback: MessageCallback, poll_hz: float
    ) -> None:
        import httpx

        period = 1.0 / max(poll_hz, 0.1)
        url = self._image_snapshot_url()
        topics = self.proxy.get("topics") or {}
        topic = topics.get("image", "/usb_cam/image_raw")
        logger.info("ppi image poll start url=%s hz=%.2f", url, poll_hz)
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
                                "topic": topic,
                            },
                        )
                    else:
                        logger.debug(
                            "ppi snapshot status=%s", r.status_code
                        )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug("ppi snapshot poll error: %s", e)
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
                name=f"ppi-sub-{modality}",
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


class MockClient(AgentClient):
    """Offline UI / queue demo without a real robot."""

    def __init__(self, proxy: dict[str, Any] | None = None) -> None:
        self.proxy = proxy or {}
        self._connected = True
        self._callbacks: dict[str, MessageCallback] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    async def connect(self) -> None:
        self._connected = True
        logger.info("ppi MockClient ready")

    async def close(self) -> None:
        for modality in list(self._tasks):
            await self.unsubscribe_message(modality)
        self._connected = False

    async def health(self) -> dict[str, Any]:
        return {
            "mode": "mock",
            "agent": "ppi_agent",
            "rosbridge": True,
            "ok": True,
        }

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cost = float(action_def.get("cost_time_sec") or 1.0)
        await asyncio.sleep(min(cost, 0.35))
        return {
            "ok": True,
            "mode": "mock",
            "agent": "ppi_agent",
            "function": action_def.get("function"),
            "params": params or {},
        }

    async def _mock_image_loop(
        self, callback: MessageCallback, poll_hz: float
    ) -> None:
        period = 1.0 / max(poll_hz, 0.1)
        topic = (self.proxy.get("topics") or {}).get("image", "/usb_cam/image_raw")
        while True:
            callback(
                "image",
                {
                    "modality": "image",
                    "stamp": time.time(),
                    "encoding": "jpeg",
                    "data": _PLACEHOLDER_JPEG,
                    "topic": topic,
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
                name="ppi-mock-image",
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


class RosbridgeClient(_ImagePollMixin, AgentClient):
    """Talk to PuppyPi via official rosbridge_websocket (port 9090)."""

    def __init__(self, proxy: dict[str, Any]) -> None:
        self.proxy = proxy
        topics = proxy.get("topics") or {}
        types = proxy.get("message_types") or {}
        self.host = str(proxy.get("ip") or "192.168.1.9")
        self.port = int(proxy.get("rosbridge_port", 9090))
        self.run_action_service = topics.get(
            "run_action_service", "/puppy_control/runActionGroup"
        )
        self.velocity_topic = topics.get("velocity", "/puppy_control/velocity")
        self.run_action_type = types.get(
            "run_action", "puppy_control/SetRunActionName"
        )
        self.velocity_type = types.get("velocity", "puppy_control/Velocity")
        self._ros = None
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, MessageCallback] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def _ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def update_host(self, host: str) -> None:
        self.host = host.strip()
        self.proxy["ip"] = self.host

    async def connect(self) -> None:
        try:
            import roslibpy  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "roslibpy is required for ppi_agent; pip install roslibpy"
            ) from e

        self.host = str(self.proxy.get("ip") or self.host).strip()
        self.port = int(self.proxy.get("rosbridge_port", self.port))

        if self._ros is not None:
            await self.close(shutdown_reactor=False)

        def _connect_sync() -> Any:
            ros = roslibpy.Ros(host=self.host, port=self.port)
            try:
                ros.run(timeout=8)
            except Exception as e:
                try:
                    ros.close()
                except Exception:
                    pass
                raise ConnectionError(
                    f"rosbridge connect failed: {self._ws_url()} ({e})"
                ) from e
            if not ros.is_connected:
                raise ConnectionError(f"rosbridge connect failed: {self._ws_url()}")
            return ros

        self._ros = await asyncio.to_thread(_connect_sync)
        logger.info("ppi Rosbridge connected %s", self._ws_url())

    async def close(self, shutdown_reactor: bool = True) -> None:
        for modality in list(self._tasks):
            await self.unsubscribe_message(modality)

        ros = self._ros
        self._ros = None
        if ros is None:
            return

        def _close_sync() -> None:
            try:
                if ros.is_connected:
                    ros.close()
            except Exception:
                pass
            if shutdown_reactor:
                try:
                    ros.terminate()
                except Exception:
                    pass

        await asyncio.to_thread(_close_sync)

    def _ensure(self) -> Any:
        if self._ros is None or not self._ros.is_connected:
            raise ConnectionError("rosbridge not connected")
        return self._ros

    async def health(self) -> dict[str, Any]:
        ok = bool(self._ros is not None and self._ros.is_connected)
        return {
            "mode": "ros",
            "agent": "ppi_agent",
            "rosbridge": ok,
            "url": self._ws_url(),
            "ok": ok,
        }

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        params = params or {}
        kind = action_def.get("kind")
        async with self._lock:
            try:
                self._ensure()
            except ConnectionError:
                await self.connect()
            if kind == "action_group":
                return await self._run_action_group(action_def)
            if kind == "velocity":
                return await self._run_velocity(action_def, params)
            raise ValueError(f"unknown action kind: {kind}")

    async def _run_action_group(self, action_def: dict[str, Any]) -> dict[str, Any]:
        import roslibpy  # type: ignore

        ros = self._ensure()
        fn = str(action_def.get("function") or "")
        ros_name = ACTION_GROUP_ALIASES.get(fn, fn)
        name = f"{ros_name}.d6ac"

        def _call() -> dict[str, Any]:
            service = roslibpy.Service(
                ros,
                self.run_action_service,
                self.run_action_type,
            )
            request = roslibpy.ServiceRequest({"name": name, "wait": True})
            result = service.call(request, timeout=60)
            return dict(result) if result is not None else {"success": True}

        result = await asyncio.to_thread(_call)
        return {
            "ok": bool(result.get("success", True)),
            "mode": "ros",
            "agent": "ppi_agent",
            "kind": "action_group",
            "name": name,
            "function": fn,
            "result": result,
        }

    def _merge_params(
        self, action_def: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for p in action_def.get("params") or []:
            name = p.get("name")
            if name and "default" in p:
                merged[name] = p["default"]
        merged.update(params)
        return merged

    async def _run_velocity(
        self, action_def: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        import roslibpy  # type: ignore

        ros = self._ensure()
        merged = self._merge_params(action_def, params)
        x = float(merged.get("x", 0.0))
        y = float(merged.get("y", 0.0))
        yaw_deg = float(merged.get("yaw_rate_deg", 0.0))
        yaw_rate = math.radians(yaw_deg)
        cost = float(action_def.get("cost_time_sec") or 2.0)
        if "angle_deg" in merged and abs(yaw_deg) > 1e-6:
            angle = abs(float(merged["angle_deg"]))
            rate_mag = abs(yaw_deg)
            cost = max(0.2, angle / rate_mag)

        def _publish(vx: float, vy: float, yaw: float) -> None:
            topic = roslibpy.Topic(
                ros,
                self.velocity_topic,
                self.velocity_type,
            )
            topic.advertise()
            topic.publish(roslibpy.Message({"x": vx, "y": vy, "yaw_rate": yaw}))
            time.sleep(0.05)
            topic.unadvertise()

        await asyncio.to_thread(_publish, x, y, yaw_rate)
        await asyncio.sleep(cost)
        await asyncio.to_thread(_publish, 0.0, 0.0, 0.0)
        return {
            "ok": True,
            "mode": "ros",
            "agent": "ppi_agent",
            "kind": "velocity",
            "function": action_def.get("function"),
            "velocity": {"x": x, "y": y, "yaw_rate_deg": yaw_deg},
            "duration_sec": cost,
        }


def create_client(proxy: dict[str, Any], mode: str = "ros") -> AgentClient:
    mode = (mode or "ros").strip().lower()
    if mode == "mock":
        return MockClient(proxy)
    if mode == "ros":
        return RosbridgeClient(proxy)
    raise ValueError(f"unsupported mode={mode!r}; use ros|mock")
