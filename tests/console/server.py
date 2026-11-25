"""PuppyPi ROS2 Web Console — camera stream + action queue API."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ros_client import RobotClient, create_client

ROOT = Path(__file__).resolve().parent
CONFIGS = ROOT / "configs"
STATIC = ROOT / "static"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("console")


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _mode() -> str:
    return os.environ.get("CONSOLE_MODE", "ros").strip().lower()


class RunBody(BaseModel):
    function: str
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectBody(BaseModel):
    host: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    robot = _load_json(CONFIGS / "robot.json")
    host_override = os.environ.get("ROBOT_HOST")
    if host_override:
        robot["robot_host"] = host_override
    mode = _mode()
    client = create_client(mode, robot)
    app.state.robot = robot
    app.state.mode = mode
    app.state.client = client
    app.state.actions = _load_json(CONFIGS / "actions.json")
    try:
        await client.connect()
    except Exception as e:
        logger.warning("robot client connect failed (mode=%s): %s", mode, e)
    yield
    try:
        await client.close()
    except Exception:
        pass


app = FastAPI(title="PuppyPi Console", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/actions")
def api_actions(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.actions)


@app.get("/api/robot")
def api_robot(request: Request) -> JSONResponse:
    robot = dict(request.app.state.robot)
    robot["mode"] = request.app.state.mode
    return JSONResponse(robot)


@app.post("/api/connect")
async def api_connect(body: ConnectBody, request: Request) -> JSONResponse:
    host = (body.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="host is required")
    # Basic sanity: hostname / IPv4 / IPv6 literal without scheme or path.
    if any(ch in host for ch in ("/", " ", "\t", "\n")) or "://" in host:
        raise HTTPException(status_code=400, detail="invalid host")

    robot = request.app.state.robot
    robot["robot_host"] = host
    client: RobotClient = request.app.state.client
    mode = request.app.state.mode
    try:
        if mode == "ros":
            await client.connect()
        health = await client.health()
        return JSONResponse(
            {
                "ok": bool(health.get("ok")),
                "robot_host": host,
                "mode": mode,
                "ros": health,
            }
        )
    except Exception as e:
        logger.exception("connect failed")
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/health")
async def api_health(request: Request) -> JSONResponse:
    client: RobotClient = request.app.state.client
    robot = request.app.state.robot
    ros_info = await client.health()
    video_ok = False
    video_url = (
        f"http://{robot['robot_host']}:{robot['web_video_port']}"
        f"/stream?topic={robot['image_topic']}"
    )
    if request.app.state.mode == "mock":
        video_ok = True
    else:
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                r = await http.get(
                    f"http://{robot['robot_host']}:{robot['web_video_port']}/",
                )
                video_ok = r.status_code < 500
        except Exception:
            video_ok = False
    return JSONResponse(
        {
            "ok": bool(ros_info.get("ok")) and (video_ok or request.app.state.mode == "mock"),
            "mode": request.app.state.mode,
            "ros": ros_info,
            "video": {"ok": video_ok, "url": video_url},
            "robot_host": robot.get("robot_host"),
        }
    )


@app.get("/api/camera/stream")
async def camera_stream(request: Request):
    """Proxy official web_video_server MJPEG for same-origin <img>."""
    if request.app.state.mode == "mock":
        return FileResponse(
            STATIC / "img" / "placeholder.svg",
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    robot = request.app.state.robot
    url = (
        f"http://{robot['robot_host']}:{robot['web_video_port']}"
        f"/stream?topic={robot['image_topic']}"
    )

    client = httpx.AsyncClient(timeout=None)
    try:
        req = client.build_request("GET", url)
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"camera unreachable: {e}") from e

    if resp.status_code != 200:
        await resp.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"camera HTTP {resp.status_code}")

    media = resp.headers.get("content-type", "multipart/x-mixed-replace;boundary=frame")

    async def gen():
        try:
            async for chunk in resp.aiter_bytes():
                if await request.is_disconnected():
                    break
                yield chunk
        except Exception as e:
            logger.warning("camera proxy error: %s", e)
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        gen(),
        media_type=media,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.post("/api/action/run")
async def action_run(body: RunBody, request: Request) -> JSONResponse:
    actions = request.app.state.actions.get("actions") or []
    action_def = next((a for a in actions if a.get("function") == body.function), None)
    if action_def is None:
        raise HTTPException(status_code=400, detail=f"unknown action: {body.function}")

    client: RobotClient = request.app.state.client
    try:
        # Reconnect once if rosbridge dropped.
        health = await client.health()
        if not health.get("ok") and request.app.state.mode == "ros":
            await client.connect()
        result = await client.run_action(action_def, body.params)
        return JSONResponse(result)
    except Exception as e:
        logger.exception("action run failed")
        raise HTTPException(status_code=502, detail=str(e)) from e
