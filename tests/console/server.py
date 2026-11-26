"""PuppyPi Web Console — load agents from src/agents/*_agent, camera + action queue."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
AGENTS_ROOT = REPO_ROOT / "src" / "agents"
STATIC = ROOT / "static"
CONFIGS = ROOT / "configs"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("console")


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _mode() -> str:
    return os.environ.get("CONSOLE_MODE", "ros").strip().lower()


def _list_agents() -> list[dict[str, str]]:
    if not AGENTS_ROOT.is_dir():
        return []
    items: list[dict[str, str]] = []
    for path in sorted(AGENTS_ROOT.iterdir()):
        if not path.is_dir():
            continue
        if not path.name.endswith("_agent"):
            continue
        proxy_path = path / "proxy" / "proxy.json"
        if not proxy_path.is_file():
            continue
        items.append({"name": path.name, "path": str(path)})
    return items


def _load_agent_module(agent_name: str):
    client_path = AGENTS_ROOT / agent_name / "src" / "client.py"
    if not client_path.is_file():
        raise FileNotFoundError(f"missing client: {client_path}")
    mod_name = f"agent_client_{agent_name}"
    spec = importlib.util.spec_from_file_location(mod_name, client_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {client_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _proxy_to_robot_view(proxy: dict[str, Any], agent_name: str, mode: str) -> dict[str, Any]:
    topics = proxy.get("topics") or {}
    return {
        "agent": agent_name,
        "ip": proxy.get("ip"),
        "robot_host": proxy.get("ip"),
        "rosbridge_port": proxy.get("rosbridge_port"),
        "web_video_port": proxy.get("web_video_port"),
        "sim_http_port": proxy.get("sim_http_port"),
        "image_topic": topics.get("image"),
        "topics": topics,
        "message_types": proxy.get("message_types") or {},
        "mode": mode,
    }


async def _close_client(client: Any) -> None:
    if client is None:
        return
    try:
        await client.close()
    except Exception:
        pass


class AgentLoadError(Exception):
    """Typed load failure for API → toast."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


async def load_agent(app: FastAPI, agent_name: str) -> dict[str, Any]:
    agent_dir = AGENTS_ROOT / agent_name
    proxy_path = agent_dir / "proxy" / "proxy.json"
    if not proxy_path.is_file():
        raise AgentLoadError(
            "proxy 缺失",
            f"未找到 proxy 文件:\n{proxy_path}",
        )

    try:
        proxy = _load_json(proxy_path)
    except json.JSONDecodeError as e:
        raise AgentLoadError(
            "proxy JSON 异常",
            f"解析失败: {proxy_path}\n"
            f"行 {e.lineno} 列 {e.colno}: {e.msg}\n"
            f"{e}",
        ) from e
    except OSError as e:
        raise AgentLoadError(
            "proxy 读取失败",
            f"无法读取 {proxy_path}\n{e}",
        ) from e

    try:
        module = _load_agent_module(agent_name)
    except Exception as e:
        raise AgentLoadError(
            "client 脚本异常",
            f"加载 {agent_name}/src/client.py 失败\n"
            f"{type(e).__name__}: {e}",
        ) from e

    mode = _mode()
    # sim_agent ignores CONSOLE_MODE; ppi uses ros|mock.
    if agent_name == "sim_agent":
        client_mode = "sim"
    else:
        client_mode = mode

    try:
        create_client = getattr(module, "create_client")
        new_client = create_client(proxy, client_mode)
    except Exception as e:
        raise AgentLoadError(
            "client 初始化异常",
            f"create_client() 失败\n{type(e).__name__}: {e}",
        ) from e

    old = getattr(app.state, "client", None)
    await _close_client(old)

    app.state.agent_name = agent_name
    app.state.proxy = proxy
    app.state.actions = {"actions": list(proxy.get("actions") or [])}
    app.state.mode = client_mode if agent_name == "sim_agent" else mode
    app.state.robot = _proxy_to_robot_view(proxy, agent_name, app.state.mode)
    app.state.client = new_client

    connect_error: str | None = None
    ip = proxy.get("ip") or ""
    try:
        await new_client.connect()
    except Exception as e:
        connect_error = (
            f"按 proxy.ip 连接失败\n"
            f"ip={ip!r}\n"
            f"{type(e).__name__}: {e}"
        )
        logger.warning("agent %s connect failed: %s", agent_name, e)

    return {
        "ok": connect_error is None,
        "agent": agent_name,
        "mode": app.state.mode,
        "actions": len(app.state.actions["actions"]),
        "robot": app.state.robot,
        "connect_error": connect_error,
        "error_kind": "连接失败" if connect_error else None,
    }


class RunBody(BaseModel):
    function: str
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectBody(BaseModel):
    host: str


class LoadAgentBody(BaseModel):
    name: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent_name = None
    app.state.proxy = {}
    app.state.actions = {"actions": []}
    app.state.client = None
    app.state.mode = _mode()
    app.state.robot = {
        "agent": None,
        "robot_host": "",
        "mode": app.state.mode,
        "image_topic": None,
        "topics": {},
    }

    default_agent = os.environ.get("CONSOLE_AGENT", "").strip()
    if default_agent:
        try:
            await load_agent(app, default_agent)
        except Exception as e:
            logger.warning("default agent load failed (%s): %s", default_agent, e)

    yield

    await _close_client(getattr(app.state, "client", None))


app = FastAPI(title="PuppyPi Console", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/agents")
def api_agents() -> JSONResponse:
    return JSONResponse({"agents": _list_agents()})


@app.post("/api/agents/load")
async def api_agents_load(body: LoadAgentBody, request: Request) -> JSONResponse:
    name = (body.name or "").strip()
    if not name.endswith("_agent"):
        raise HTTPException(status_code=400, detail="name must end with _agent")
    if any(ch in name for ch in ("/", "\\", "..", " ")):
        raise HTTPException(status_code=400, detail="invalid agent name")
    try:
        result = await load_agent(request.app, name)
        health = {"ok": False}
        client = request.app.state.client
        if client is not None:
            try:
                health = await client.health()
            except Exception as e:
                health = {"ok": False, "error": str(e)}
        result["health"] = health
        # Connect failures still return 200 so UI can show toast + keep actions.
        return JSONResponse(result)
    except AgentLoadError as e:
        logger.exception("load agent failed (%s)", e.kind)
        return JSONResponse(
            {
                "ok": False,
                "error_kind": e.kind,
                "detail": e.message,
            },
            status_code=400,
        )
    except FileNotFoundError as e:
        return JSONResponse(
            {"ok": False, "error_kind": "文件缺失", "detail": str(e)},
            status_code=404,
        )
    except Exception as e:
        logger.exception("load agent failed")
        return JSONResponse(
            {
                "ok": False,
                "error_kind": "未知异常",
                "detail": f"{type(e).__name__}: {e}",
            },
            status_code=502,
        )


@app.get("/api/actions")
def api_actions(request: Request) -> JSONResponse:
    return JSONResponse(request.app.state.actions)


@app.get("/api/robot")
def api_robot(request: Request) -> JSONResponse:
    robot = dict(request.app.state.robot)
    robot["mode"] = request.app.state.mode
    robot["agent"] = request.app.state.agent_name
    return JSONResponse(robot)


@app.post("/api/connect")
async def api_connect(body: ConnectBody, request: Request) -> JSONResponse:
    host = (body.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="host is required")
    if any(ch in host for ch in ("/", " ", "\t", "\n")) or "://" in host:
        raise HTTPException(status_code=400, detail="invalid host")

    if request.app.state.client is None or not request.app.state.agent_name:
        raise HTTPException(status_code=400, detail="load an agent first")

    proxy = request.app.state.proxy
    proxy["ip"] = host
    request.app.state.robot["ip"] = host
    request.app.state.robot["robot_host"] = host

    client = request.app.state.client
    if hasattr(client, "update_host"):
        client.update_host(host)
    try:
        await client.connect()
        health = await client.health()
        return JSONResponse(
            {
                "ok": bool(health.get("ok")),
                "robot_host": host,
                "agent": request.app.state.agent_name,
                "mode": request.app.state.mode,
                "ros": health,
            }
        )
    except Exception as e:
        logger.exception("connect failed")
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/health")
async def api_health(request: Request) -> JSONResponse:
    agent_name = request.app.state.agent_name
    robot = request.app.state.robot
    client = request.app.state.client
    if client is None or not agent_name:
        return JSONResponse(
            {
                "ok": False,
                "mode": request.app.state.mode,
                "agent": None,
                "ros": {"ok": False},
                "video": {"ok": False, "url": None},
                "robot_host": robot.get("robot_host") or robot.get("ip"),
                "detail": "no agent loaded",
            }
        )

    ros_info = await client.health()
    topics = robot.get("topics") or {}
    image_topic = topics.get("image") or robot.get("image_topic")
    host = robot.get("robot_host") or robot.get("ip")
    video_ok = False
    video_url = None

    if request.app.state.mode == "mock" and agent_name != "sim_agent":
        video_ok = True
        video_url = "/static/img/placeholder.svg"
    elif agent_name in ("ppi_agent", "sim_agent"):
        web_video_port = (
            robot.get("web_video_port")
            or robot.get("sim_http_port")
            or (8765 if agent_name == "sim_agent" else 8080)
        )
        video_url = f"http://{host}:{web_video_port}/stream?topic={image_topic}"
        if agent_name == "sim_agent":
            # Prefer sim health.image_ok (fresh head-camera frame).
            video_ok = bool(ros_info.get("image_ok"))
            if not video_ok and ros_info.get("ok"):
                try:
                    async with httpx.AsyncClient(timeout=1.0) as http:
                        r = await http.get(
                            f"http://{host}:{web_video_port}/api/health"
                        )
                        if r.status_code == 200:
                            video_ok = bool(r.json().get("image_ok"))
                except Exception:
                    video_ok = False
        else:
            try:
                async with httpx.AsyncClient(timeout=2.0) as http:
                    r = await http.get(f"http://{host}:{web_video_port}/")
                    video_ok = r.status_code < 500
            except Exception:
                video_ok = False
    else:
        video_ok = False
        video_url = None

    ok = bool(ros_info.get("ok"))
    if agent_name == "ppi_agent" and request.app.state.mode != "mock":
        ok = ok and video_ok

    return JSONResponse(
        {
            "ok": ok,
            "mode": request.app.state.mode,
            "agent": agent_name,
            "ros": ros_info,
            "video": {"ok": video_ok, "url": video_url},
            "robot_host": host,
        }
    )


@app.get("/api/camera/stream")
async def camera_stream(request: Request):
    """Proxy web_video_server / sim MJPEG for same-origin <img>."""
    agent_name = request.app.state.agent_name
    mode = request.app.state.mode

    if agent_name is None or (mode == "mock" and agent_name != "sim_agent"):
        return FileResponse(
            STATIC / "img" / "placeholder.svg",
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    if agent_name not in ("ppi_agent", "sim_agent"):
        return FileResponse(
            STATIC / "img" / "placeholder.svg",
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    robot = request.app.state.robot
    topics = robot.get("topics") or {}
    default_topic = (
        "/sim_dog/image_raw" if agent_name == "sim_agent" else "/usb_cam/image_raw"
    )
    image_topic = topics.get("image") or robot.get("image_topic") or default_topic
    host = robot.get("robot_host") or robot.get("ip")
    port = robot.get("web_video_port") or robot.get("sim_http_port") or (
        8765 if agent_name == "sim_agent" else 8080
    )
    url = f"http://{host}:{port}/stream?topic={image_topic}"

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
    if request.app.state.client is None or not request.app.state.agent_name:
        raise HTTPException(status_code=400, detail="load an agent first")

    actions = request.app.state.actions.get("actions") or []
    action_def = next((a for a in actions if a.get("function") == body.function), None)
    if action_def is None:
        raise HTTPException(status_code=400, detail=f"unknown action: {body.function}")

    client = request.app.state.client
    try:
        health = await client.health()
        if not health.get("ok"):
            await client.connect()
        result = await client.run_action(action_def, body.params)
        return JSONResponse(result)
    except Exception as e:
        logger.exception("action run failed")
        raise HTTPException(status_code=502, detail=str(e)) from e
