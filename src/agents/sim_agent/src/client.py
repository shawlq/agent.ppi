"""sim_agent client — ROS-shaped commands over local sim HTTP gateway."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SimAgentClient:
    """Publish /sim_dog/command to the local sim server (no system rosbridge)."""

    def __init__(self, proxy: dict[str, Any]) -> None:
        self.proxy = proxy
        self.host = str(proxy.get("ip") or "127.0.0.1")
        self.port = int(proxy.get("sim_http_port", 8765))
        topics = proxy.get("topics") or {}
        self.command_topic = topics.get("command", "/sim_dog/command")
        self._ok = False

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def update_host(self, host: str) -> None:
        self.host = host.strip()
        self.proxy["ip"] = self.host

    async def connect(self) -> None:
        health = await self.health()
        if not health.get("ok"):
            raise ConnectionError(
                f"sim gateway unreachable: {self.base_url}/api/health"
            )
        self._ok = True
        logger.info("sim_agent connected %s", self.base_url)

    async def close(self) -> None:
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
                    "sim": data,
                }
        except Exception as e:
            self._ok = False
            return {
                "mode": "sim",
                "agent": "sim_agent",
                "ok": False,
                "url": url,
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


def create_client(proxy: dict[str, Any], mode: str = "sim") -> SimAgentClient:
    # mode kept for API symmetry with ppi_agent; sim always uses HTTP gateway.
    _ = mode
    return SimAgentClient(proxy)
