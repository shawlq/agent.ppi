"""Build VLM/LLM clients from this agent's models.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.model_clients import OpenAICompatLLM, OpenAICompatVLM

from .mock import MockLLM, MockVLM

logger = logging.getLogger(__name__)

_DEFAULT_MODELS = Path(__file__).resolve().parent / "models.json"


def load_models_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else _DEFAULT_MODELS
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


def _openai_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "base_url": str(cfg["base_url"]),
        "model": str(cfg["model"]),
        "api_key": str(cfg.get("api_key") or "EMPTY"),
        "timeout_sec": float(cfg.get("timeout_sec") or 60),
        "max_tokens": int(cfg.get("max_tokens") or 2048),
        "extra_body": dict(cfg.get("extra_body") or {}),
    }


def create_vlm(cfg: dict[str, Any]):
    mode = str(cfg.get("mode") or "mock").strip().lower()
    if mode == "mock":
        logger.info("VLM mode=mock")
        return MockVLM()
    if mode in ("openai", "openai_compat", "http"):
        logger.info("VLM mode=openai model=%s", cfg.get("model"))
        return OpenAICompatVLM(**_openai_kwargs(cfg))
    raise ValueError(f"unsupported vlm mode={mode!r}")


def create_llm(cfg: dict[str, Any]):
    mode = str(cfg.get("mode") or "mock").strip().lower()
    if mode == "mock":
        logger.info("LLM mode=mock")
        return MockLLM()
    if mode in ("openai", "openai_compat", "http"):
        logger.info("LLM mode=openai model=%s", cfg.get("model"))
        return OpenAICompatLLM(**_openai_kwargs(cfg))
    raise ValueError(f"unsupported llm mode={mode!r}")
