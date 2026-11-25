"""PuppyPi home-scene 3D web sim — FastAPI static + JSON config server."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
CONFIGS = ROOT / "configs"
STATIC = ROOT / "static"

app = FastAPI(title="PuppyPi 3D Sim", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/scene")
def api_scene() -> FileResponse:
    return FileResponse(CONFIGS / "scene_home.json", media_type="application/json")


@app.get("/api/actions")
def api_actions() -> FileResponse:
    return FileResponse(CONFIGS / "actions.json", media_type="application/json")


@app.get("/api/ui")
def api_ui() -> FileResponse:
    return FileResponse(CONFIGS / "ui.json", media_type="application/json")
