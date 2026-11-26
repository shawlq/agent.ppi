"""Load markdown templates and merge into prompts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


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


def environment_to_text(env: Any) -> str:
    if isinstance(env, str):
        return env
    import json

    return json.dumps(env, ensure_ascii=False, indent=2)
