"""Load agent proxy.json and create_client without importing concrete agents."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = REPO_ROOT / "src" / "agents"


def load_proxy(agent_name: str) -> dict[str, Any]:
    path = AGENTS_ROOT / agent_name / "proxy" / "proxy.json"
    if not path.is_file():
        raise FileNotFoundError(f"proxy not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_client_module(agent_name: str):
    client_path = AGENTS_ROOT / agent_name / "src" / "client.py"
    if not client_path.is_file():
        raise FileNotFoundError(f"missing client: {client_path}")
    mod_name = f"runtime_agent_client_{agent_name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, client_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {client_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def create_agent_client(agent_name: str, mode: str | None = None) -> tuple[dict[str, Any], Any]:
    """Return (proxy, client)."""
    proxy = load_proxy(agent_name)
    module = load_client_module(agent_name)
    create_client = getattr(module, "create_client", None)
    if create_client is None:
        raise AttributeError(f"{agent_name} client.py missing create_client")
    if mode is None:
        mode = "sim" if agent_name == "sim_agent" else "ros"
    client = create_client(proxy, mode)
    logger.info("loaded agent=%s mode=%s", agent_name, mode)
    return proxy, client
