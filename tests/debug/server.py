"""Runtime debug web UI — independent of tests/console."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
AGENTS_ROOT = REPO_ROOT / "src" / "agents"
STATIC = ROOT / "static"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.service import RuntimeService  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("debug")


def _list_agents() -> list[dict[str, str]]:
    if not AGENTS_ROOT.is_dir():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(AGENTS_ROOT.iterdir()):
        if not path.is_dir() or not path.name.endswith("_agent"):
            continue
        if (path / "proxy" / "proxy.json").is_file():
            items.append({"name": path.name, "path": str(path)})
    return items


class ConnectBody(BaseModel):
    agent: str = Field(default="sim_agent")
    client_mode: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = RuntimeService()
    app.state.sse_queues: list[asyncio.Queue] = []
    yield
    rt: RuntimeService = app.state.runtime
    await rt.stop()


app = FastAPI(title="PPI Runtime Debug", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _broadcast(app: FastAPI, snap: dict[str, Any]) -> None:
    for q in list(getattr(app.state, "sse_queues", []) or []):
        try:
            q.put_nowait(snap)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(snap)
            except asyncio.QueueFull:
                pass


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/agents")
def api_agents() -> JSONResponse:
    return JSONResponse({"agents": _list_agents()})


@app.get("/api/status")
def api_status(request: Request) -> JSONResponse:
    rt: RuntimeService = request.app.state.runtime
    return JSONResponse(rt.status())


@app.post("/api/connect")
async def api_connect(body: ConnectBody, request: Request) -> JSONResponse:
    name = (body.agent or "sim_agent").strip()
    if not name.endswith("_agent"):
        raise HTTPException(status_code=400, detail="agent must end with _agent")
    if any(ch in name for ch in ("/", "\\", "..", " ")):
        raise HTTPException(status_code=400, detail="invalid agent name")
    if not (AGENTS_ROOT / name / "proxy" / "proxy.json").is_file():
        raise HTTPException(status_code=404, detail=f"unknown agent {name}")

    rt: RuntimeService = request.app.state.runtime
    old_cb = getattr(request.app.state, "debug_cb", None)
    if old_cb is not None:
        rt.debug_hub.unregister(old_cb)
        request.app.state.debug_cb = None

    def on_debug(snap: dict[str, Any]) -> None:
        _broadcast(request.app, snap)

    rt.debug_hub.register(on_debug)
    try:
        status = await rt.start(
            agent_name=name,
            client_mode=body.client_mode,
        )
    except Exception as e:
        rt.debug_hub.unregister(on_debug)
        logger.exception("connect/start failed")
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}") from e

    request.app.state.debug_cb = on_debug
    return JSONResponse({"ok": True, **status})


@app.post("/api/disconnect")
async def api_disconnect(request: Request) -> JSONResponse:
    rt: RuntimeService = request.app.state.runtime
    cb = getattr(request.app.state, "debug_cb", None)
    if cb is not None:
        rt.debug_hub.unregister(cb)
        request.app.state.debug_cb = None
    await rt.stop()
    return JSONResponse({"ok": True, **rt.status()})


@app.get("/api/debug/latest")
def api_debug_latest(request: Request) -> JSONResponse:
    rt: RuntimeService = request.app.state.runtime
    latest = rt.debug_hub.latest()
    return JSONResponse({"ok": True, "snapshot": latest})


@app.get("/api/debug/image/{name}")
def api_debug_image(name: str, request: Request) -> Response:
    if not name or any(ch in name for ch in ("/", "\\", "..", " ")):
        raise HTTPException(status_code=400, detail="invalid image name")
    rt: RuntimeService = request.app.state.runtime
    data = rt.debug_hub.get_image(name)
    if not data:
        raise HTTPException(status_code=404, detail="no image yet")
    return Response(content=data, media_type="image/jpeg")


@app.get("/api/debug/stream")
async def api_debug_stream(request: Request) -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue(maxsize=8)
    request.app.state.sse_queues.append(queue)
    rt: RuntimeService = request.app.state.runtime
    latest = rt.debug_hub.latest()
    if latest:
        try:
            queue.put_nowait(latest)
        except asyncio.QueueFull:
            pass

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    snap = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = json.dumps(snap, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            try:
                request.app.state.sse_queues.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
