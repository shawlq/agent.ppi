"""Parse LLM text into a validated action list against the proxy whitelist."""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def extract_json_array(text: str) -> list[Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("actions"), list):
            return data["actions"]
    except json.JSONDecodeError:
        pass
    m = _JSON_ARRAY_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else None
    except json.JSONDecodeError:
        return None


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


def extract_reason(text: str) -> str | None:
    obj = extract_json_object(text)
    if obj is None:
        return None
    for key in ("reason", "why", "rationale"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def parse_actions(
    llm_text: str,
    allowed_actions: list[dict[str, Any]],
    min_actions: int = 3,
    max_actions: int = 5,
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """Registered callback: LLM text → (valid items, errors, reason)."""
    by_fn = {
        str(a.get("function")): a for a in allowed_actions if a.get("function")
    }
    errors: list[str] = []
    reason = extract_reason(llm_text)
    raw = extract_json_array(llm_text)
    if raw is None:
        errors.append("LLM output is not a JSON array/actions object")
        return [], errors, reason

    valid: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"item[{i}] not an object")
            continue
        fn = item.get("function") or item.get("cmd")
        if not fn or not isinstance(fn, str):
            errors.append(f"item[{i}] missing function")
            continue
        action_def = by_fn.get(fn)
        if action_def is None:
            errors.append(f"item[{i}] unknown function={fn!r}")
            continue
        params = item.get("params") or item.get("args") or {}
        if params is None:
            params = {}
        if not isinstance(params, dict):
            errors.append(f"item[{i}] params must be object")
            continue
        ok_params = True
        for p in action_def.get("params") or []:
            name = p.get("name")
            if not name or name not in params:
                continue
            if p.get("type") == "number":
                try:
                    params[name] = float(params[name])
                except (TypeError, ValueError):
                    errors.append(f"item[{i}] param {name} not number")
                    ok_params = False
                    break
        if not ok_params:
            continue
        valid.append({"action_def": action_def, "params": params})

    if len(valid) > max_actions:
        errors.append(f"truncated sequence from {len(valid)} to {max_actions}")
        valid = valid[:max_actions]
    if 0 < len(valid) < min_actions:
        errors.append(
            f"sequence shorter than min_actions={min_actions} "
            f"(got {len(valid)}); still accepting"
        )
    return valid, errors, reason
