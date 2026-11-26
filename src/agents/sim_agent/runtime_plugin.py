"""Register sim_agent domain hooks with the agent_runtime framework."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from src.registry import AgentSpec

_ROOT = Path(__file__).resolve().parent
_PREFIX = "sim_agent_plugin"


def _load_module(mod_name: str, path: Path):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _load_model_package():
    """Load model/ as a uniquely named package so both agents can coexist."""
    pkg_name = f"{_PREFIX}_model"
    if pkg_name not in sys.modules:
        pkg = types.ModuleType(pkg_name)
        pkg.__path__ = [str(_ROOT / "model")]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg
    mock = _load_module(f"{pkg_name}.mock", _ROOT / "model" / "mock.py")
    # factory imports `.mock` and `src.model_clients`
    factory = _load_module(f"{pkg_name}.factory", _ROOT / "model" / "factory.py")
    return factory


def _load_create_client():
    module = _load_module(f"{_PREFIX}_client", _ROOT / "src" / "client.py")
    return module.create_client


def build_agent_spec() -> AgentSpec:
    fuse = _load_module(f"{_PREFIX}_fuse", _ROOT / "fuse.py")
    parse = _load_module(f"{_PREFIX}_parse", _ROOT / "parse_actions.py")
    factory = _load_model_package()
    prompts = _ROOT / "prompts"
    return AgentSpec(
        name="sim_agent",
        default_client_mode="sim",
        create_client=_load_create_client(),
        create_vlm=factory.create_vlm,
        create_llm=factory.create_llm,
        load_models_config=lambda: factory.load_models_config(
            _ROOT / "model" / "models.json"
        ),
        identity_text=(prompts / "identity.md").read_text(encoding="utf-8"),
        env_template=(prompts / "env_template.md").read_text(encoding="utf-8"),
        fuse_prompt=fuse.fuse_prompt,
        parse_actions=parse.parse_actions,
    )
