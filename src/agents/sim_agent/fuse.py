"""Fuse RuntimeContext + VLM output into the LLM action prompt."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROMPTS = Path(__file__).resolve().parent / "prompts"
_ACTION_TEMPLATE = (_PROMPTS / "action_prompt.md").read_text(encoding="utf-8")


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def environment_to_text(env: Any) -> str:
    if isinstance(env, str):
        return env
    return json.dumps(env, ensure_ascii=False, indent=2)


def render_template(template: str, **fields: str) -> str:
    out = template
    for key, value in fields.items():
        out = out.replace("{{" + key + "}}", value)
    return out


def build_action_prompt(
    template: str,
    *,
    identity: str,
    environment: str,
    history: str,
    allowed_actions: str,
) -> str:
    return render_template(
        template,
        identity=identity,
        environment=environment,
        history=history,
        allowed_actions=allowed_actions,
    )


def fuse_prompt(context: Any, env_raw: str, env_obj: dict[str, Any] | None = None) -> str:
    """Registered callback: context + VLM → LLM prompt string."""
    parsed = env_obj if env_obj is not None else extract_json_object(env_raw)
    env_text = environment_to_text(parsed if parsed is not None else env_raw)
    sections = context.to_prompt_sections()
    return build_action_prompt(
        _ACTION_TEMPLATE,
        identity=sections["identity"],
        environment=env_text,
        history=sections["history"],
        allowed_actions=sections["allowed_actions"],
    )
