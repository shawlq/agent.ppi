"""PuppyPi home-scene 3D web sim — config API + ROS-shaped command gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
CONFIGS = ROOT / "configs"
STATIC = ROOT / "static"
SIM_PROXY = REPO_ROOT / "src" / "agents" / "sim_agent" / "proxy" / "proxy.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sim")

COMMAND_TOPIC = "/sim_dog/command"


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _actions_payload() -> dict[str, Any]:
    if SIM_PROXY.is_file():
        proxy = _load_json(SIM_PROXY)
        return {"actions": list(proxy.get("actions") or [])}
    return _load_json(CONFIGS / "actions.json")


class RosCommandBody(BaseModel):
    topic: str
    data: dict[str, Any] = Field(default_factory=dict)


class CommandHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        logger.info("ws client connected (%d)", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
        logger.info("ws client disconnected (%d)", len(self._clients))

    async def broadcast(self, message: dict[str, Any]) -> int:
        raw = json.dumps(message, ensure_ascii=False)
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        sent = 0
        for ws in clients:
            try:
                await ws.send_text(raw)
                sent += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        return sent


hub = CommandHub()
app = FastAPI(title="PuppyPi 3D Sim", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/scene")
def api_scene() -> FileResponse:
    return FileResponse(CONFIGS / "scene_home.json", media_type="application/json")


@app.get("/api/actions")
def api_actions() -> JSONResponse:
    return JSONResponse(_actions_payload())


@app.get("/api/ui")
def api_ui() -> FileResponse:
    return FileResponse(CONFIGS / "ui.json", media_type="application/json")


@app.get("/api/health")
def api_health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "service": "sim",
            "command_topic": COMMAND_TOPIC,
            "ws_clients": len(hub._clients),
        }
    )


@app.post("/api/ros/command")
async def api_ros_command(body: RosCommandBody) -> JSONResponse:
    topic = (body.topic or "").strip()
    if topic != COMMAND_TOPIC:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported topic: {topic}; expected {COMMAND_TOPIC}",
        )
    data = body.data or {}
    fn = data.get("function")
    if not fn:
        raise HTTPException(status_code=400, detail="data.function is required")

    message = {
        "topic": topic,
        "function": fn,
        "params": data.get("params") or {},
        "cost_time_sec": float(data.get("cost_time_sec") or 1.0),
    }
    sent = await hub.broadcast(message)
    logger.info("command %s → %d ws client(s)", fn, sent)
    return JSONResponse({"ok": True, "delivered": sent, "command": message})


@app.websocket("/ws/commands")
async def ws_commands(ws: WebSocket) -> None:
    await hub.connect(ws)
    try:
        while True:
            # Keepalive / ignore client messages.
            await ws.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect(ws)
    except Exception:
        await hub.disconnect(ws)
