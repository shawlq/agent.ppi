"""PuppyPi home-scene 3D web sim — config API + ROS-shaped command/image gateway."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
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
IMAGE_TOPIC = "/sim_dog/image_raw"
IMAGE_STALE_SEC = 1.0
MJPEG_BOUNDARY = "frame"


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _actions_payload() -> dict[str, Any]:
    if SIM_PROXY.is_file():
        proxy = _load_json(SIM_PROXY)
        return {"actions": list(proxy.get("actions") or [])}
    return _load_json(CONFIGS / "actions.json")


def _image_topic_from_proxy() -> str:
    if SIM_PROXY.is_file():
        proxy = _load_json(SIM_PROXY)
        topics = proxy.get("topics") or {}
        topic = topics.get("image")
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    return IMAGE_TOPIC


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


class ImageHub:
    """Latest JPEG frame per topic (browser head-camera → MJPEG consumers)."""

    def __init__(self, stale_sec: float = IMAGE_STALE_SEC) -> None:
        self._stale_sec = stale_sec
        self._lock = asyncio.Lock()
        self._frames: dict[str, dict[str, Any]] = {}
        self._events: dict[str, asyncio.Event] = {}

    def _event(self, topic: str) -> asyncio.Event:
        ev = self._events.get(topic)
        if ev is None:
            ev = asyncio.Event()
            self._events[topic] = ev
        return ev

    async def put(
        self,
        topic: str,
        jpeg: bytes,
        *,
        width: int,
        height: int,
        encoding: str = "jpeg",
    ) -> None:
        async with self._lock:
            self._frames[topic] = {
                "jpeg": jpeg,
                "width": width,
                "height": height,
                "encoding": encoding,
                "stamp": time.monotonic(),
            }
            ev = self._event(topic)
            ev.set()

    async def get(self, topic: str) -> dict[str, Any] | None:
        async with self._lock:
            frame = self._frames.get(topic)
            if frame is None:
                return None
            age = time.monotonic() - float(frame["stamp"])
            if age > self._stale_sec:
                return None
            return {
                "jpeg": frame["jpeg"],
                "width": frame["width"],
                "height": frame["height"],
                "encoding": frame["encoding"],
                "stamp": frame["stamp"],
            }

    def image_ok(self, topic: str) -> bool:
        frame = self._frames.get(topic)
        if frame is None:
            return False
        return (time.monotonic() - float(frame["stamp"])) <= self._stale_sec

    async def wait_frame(self, topic: str, timeout: float = 1.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while True:
            frame = await self.get(topic)
            if frame is not None:
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            async with self._lock:
                existing = self._frames.get(topic)
                if existing is not None:
                    age = time.monotonic() - float(existing["stamp"])
                    if age <= self._stale_sec:
                        return {
                            "jpeg": existing["jpeg"],
                            "width": existing["width"],
                            "height": existing["height"],
                            "encoding": existing["encoding"],
                            "stamp": existing["stamp"],
                        }
                ev = self._event(topic)
                # Clear before waiting so we only wake on a new put.
                if ev.is_set():
                    ev.clear()
            try:
                await asyncio.wait_for(ev.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                return await self.get(topic)


hub = CommandHub()
image_hub = ImageHub()
app = FastAPI(title="PuppyPi 3D Sim", version="0.3.0")
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
    image_topic = _image_topic_from_proxy()
    return JSONResponse(
        {
            "ok": True,
            "service": "sim",
            "command_topic": COMMAND_TOPIC,
            "image_topic": image_topic,
            "image_ok": image_hub.image_ok(image_topic),
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


@app.post("/api/ros/image")
async def api_ros_image(
    topic: str = Form(...),
    encoding: str = Form("jpeg"),
    width: int = Form(640),
    height: int = Form(480),
    frame: UploadFile = File(...),
) -> JSONResponse:
    expected = _image_topic_from_proxy()
    topic = (topic or "").strip()
    if topic != expected:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported topic: {topic}; expected {expected}",
        )
    enc = (encoding or "jpeg").strip().lower()
    if enc not in ("jpeg", "jpg"):
        raise HTTPException(status_code=400, detail="encoding must be jpeg")
    raw = await frame.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty frame")
    await image_hub.put(
        topic,
        raw,
        width=max(1, int(width)),
        height=max(1, int(height)),
        encoding="jpeg",
    )
    return JSONResponse(
        {"ok": True, "topic": topic, "bytes": len(raw), "width": width, "height": height}
    )


@app.get("/stream")
async def stream_mjpeg(request: Request, topic: str | None = None) -> StreamingResponse:
    """web_video_server-compatible MJPEG: /stream?topic=/sim_dog/image_raw"""
    expected = _image_topic_from_proxy()
    topic = (topic or expected).strip()
    if topic != expected:
        raise HTTPException(
            status_code=404,
            detail=f"unknown topic: {topic}; expected {expected}",
        )

    async def gen():
        # Wait briefly for the first frame so <img> does not fail immediately
        # when the sim page has just opened.
        first = await image_hub.wait_frame(topic, timeout=2.0)
        if first is None:
            return
        while True:
            if await request.is_disconnected():
                break
            frame = await image_hub.get(topic)
            if frame is None:
                frame = await image_hub.wait_frame(topic, timeout=1.0)
            if frame is None:
                continue
            jpeg: bytes = frame["jpeg"]
            header = (
                f"--{MJPEG_BOUNDARY}\r\n"
                f"Content-Type: image/jpeg\r\n"
                f"Content-Length: {len(jpeg)}\r\n\r\n"
            ).encode("ascii")
            yield header + jpeg + b"\r\n"
            await asyncio.sleep(0.05)

    media = f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"
    return StreamingResponse(
        gen(),
        media_type=media,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/snapshot")
async def snapshot(topic: str | None = None) -> Response:
    expected = _image_topic_from_proxy()
    topic = (topic or expected).strip()
    frame = await image_hub.get(topic)
    if frame is None:
        raise HTTPException(status_code=503, detail="no fresh image frame")
    return Response(
        content=frame["jpeg"],
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


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
