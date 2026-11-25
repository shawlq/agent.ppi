"""PuppyPi action client for console — rosbridge (ROS1/ROS2) or mock."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class RobotClient(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def health(self) -> dict[str, Any]: ...

    @abstractmethod
    async def run_action(self, action_def: dict[str, Any], params: dict[str, Any] | None = None) -> dict[str, Any]: ...


class MockClient(RobotClient):
    """Offline UI / queue demo without a real robot."""

    def __init__(self) -> None:
        self._connected = True

    async def connect(self) -> None:
        self._connected = True
        logger.info("MockClient ready")

    async def close(self) -> None:
        self._connected = False

    async def health(self) -> dict[str, Any]:
        return {"mode": "mock", "rosbridge": True, "ok": True}

    async def run_action(
        self, action_def: dict[str, Any], params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        cost = float(action_def.get("cost_time_sec") or 1.0)
        await asyncio.sleep(min(cost, 0.35))
        return {
            "ok": True,
            "mode": "mock",
            "function": action_def.get("function"),
            "params": params or {},
        }


class RosbridgeClient(RobotClient):
    """Talk to PuppyPi via official rosbridge_websocket (port 9090)."""

    def __init__(self, robot: dict[str, Any]) -> None:
        self.robot = robot
        self.host = robot.get("robot_host", "192.168.1.9")
        self.port = int(robot.get("rosbridge_port", 9090))
        self.run_action_service = robot.get(
            "run_action_service", "/puppy_control/runActionGroup"
        )
        self.velocity_topic = robot.get("velocity_topic", "/puppy_control/velocity")
        # ROS1 Noetic on device uses puppy_control/* (not puppy_control_msgs/*).
        self.run_action_type = robot.get(
            "run_action_type", "puppy_control/SetRunActionName"
        )
        self.velocity_type = robot.get("velocity_type", "puppy_control/Velocity")
        self._ros = None
        self._lock = asyncio.Lock()

    def _ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def connect(self) -> None:
        try:
            import roslibpy  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "roslibpy is required for CONSOLE_MODE=ros; pip install roslibpy"
            ) from e

        # Pick up host/port changes from shared robot config.
        self.host = str(self.robot.get("robot_host") or self.host).strip()
        self.port = int(self.robot.get("rosbridge_port", self.port))

        # Drop stale websocket only — do NOT terminate Twisted reactor
        # (ReactorNotRestartable prevents later reconnects in-process).
        if self._ros is not None:
            await self.close(shutdown_reactor=False)

        def _connect_sync() -> Any:
            ros = roslibpy.Ros(host=self.host, port=self.port)
            # run() starts reactor once; subsequent calls just wait for ready.
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
        logger.info("Rosbridge connected %s", self._ws_url())

    async def close(self, shutdown_reactor: bool = True) -> None:
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
            # Only stop Twisted on process shutdown; reconnect needs reactor alive.
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
            # Reconnect if bridge dropped.
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
        ros_name = action_def.get("ros_name") or action_def.get("function")
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
            "kind": "action_group",
            "name": name,
            "result": result,
        }

    async def _run_velocity(
        self, action_def: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        import roslibpy  # type: ignore

        ros = self._ensure()
        vel = dict(action_def.get("velocity") or {})
        if "yaw_rate_deg" in params:
            vel["yaw_rate_deg"] = float(params["yaw_rate_deg"])
        x = float(vel.get("x", 0.0))
        y = float(vel.get("y", 0.0))
        yaw_deg = float(vel.get("yaw_rate_deg", 0.0))
        yaw_rate = math.radians(yaw_deg)
        cost = float(action_def.get("cost_time_sec") or 2.0)
        # angle_deg → duration at configured yaw rate (default 90° ≈ cost_time_sec)
        if "angle_deg" in params and abs(yaw_deg) > 1e-6:
            angle = abs(float(params["angle_deg"]))
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
            "kind": "velocity",
            "function": action_def.get("function"),
            "velocity": {"x": x, "y": y, "yaw_rate_deg": yaw_deg},
            "duration_sec": cost,
        }


def create_client(mode: str, robot: dict[str, Any]) -> RobotClient:
    mode = (mode or "ros").strip().lower()
    if mode == "mock":
        return MockClient()
    if mode == "ros":
        return RosbridgeClient(robot)
    raise ValueError(f"unsupported CONSOLE_MODE={mode!r}; use ros|mock")
