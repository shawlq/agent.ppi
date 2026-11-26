"""Periodic think loop: DF → VLM → prompt → LLM → validate → executor.replace."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from .context import RuntimeContext
from .dataframe import DataFrame
from .debug import DebugHub
from .executor import ActionExecutor
from .inbox import MessageInbox
from .prompt import build_action_prompt, environment_to_text, load_text
from .validator import ActionValidator, extract_json_object

logger = logging.getLogger(__name__)


class ThinkLoop:
    def __init__(
        self,
        *,
        inbox: MessageInbox,
        context: RuntimeContext,
        executor: ActionExecutor,
        vlm: Any,
        llm: Any,
        env_template: str,
        action_template: str,
        think_hz: float = 0.2,
        min_actions: int = 3,
        max_actions: int = 5,
        max_rounds: int | None = None,
        debug_hub: DebugHub | None = None,
    ) -> None:
        self.inbox = inbox
        self.context = context
        self.executor = executor
        self.vlm = vlm
        self.llm = llm
        self.env_template = env_template
        self.action_template = action_template
        self.period = 1.0 / max(think_hz, 1e-6)
        self.validator = ActionValidator(
            context.allowed_actions,
            min_actions=min_actions,
            max_actions=max_actions,
        )
        self.max_rounds = max_rounds
        self.debug_hub = debug_hub
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self.rounds_done = 0

    def start(self) -> None:
        self._stop.clear()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name="think-loop")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run(self) -> None:
        logger.info("think loop started period=%.2fs", self.period)
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                await self._one_round()
            except Exception:
                logger.exception("think round failed")
            self.rounds_done += 1
            if self.max_rounds is not None and self.rounds_done >= self.max_rounds:
                logger.info("think loop reached max_rounds=%d", self.max_rounds)
                break
            elapsed = time.monotonic() - t0
            wait = max(0.0, self.period - elapsed)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
                break
            except asyncio.TimeoutError:
                pass
        logger.info("think loop stopped rounds=%d", self.rounds_done)

    async def _one_round(self) -> None:
        df = DataFrame.from_inbox(self.inbox)
        if df is None or not df.has_image:
            logger.info("think skip: no image yet")
            return

        env_raw = await self.vlm.describe(
            image_bytes=df.image_bytes,
            image_path=df.image_path,
            instruction=self.env_template,
        )
        env_obj = extract_json_object(env_raw)
        env_text = environment_to_text(env_obj if env_obj is not None else env_raw)
        logger.info("VLM env summary=%s", (env_obj or {}).get("summary", env_text[:120]))

        sections = self.context.to_prompt_sections()
        prompt = build_action_prompt(
            self.action_template,
            identity=sections["identity"],
            environment=env_text,
            history=sections["history"],
            allowed_actions=sections["allowed_actions"],
        )
        llm_raw = await self.llm.complete(prompt)
        valid, errors = self.validator.parse_and_validate(llm_raw)
        for err in errors:
            logger.warning("validator: %s", err)

        if self.debug_hub is not None:
            self.debug_hub.emit_round(
                df_jpeg=df.image_bytes,
                vlm_raw=env_raw if isinstance(env_raw, str) else str(env_raw),
                vlm_parsed=env_obj,
                context={
                    "identity": sections["identity"],
                    "history": self.context.history(),
                    "allowed_actions": self.context.allowed_actions_brief(),
                },
                prompt=prompt,
                llm_raw=llm_raw if isinstance(llm_raw, str) else str(llm_raw),
                actions_valid=valid,
                errors=errors,
            )

        if not valid:
            logger.warning("no valid actions this round; skip replace")
            return

        logger.info(
            "executor replace n=%d functions=%s",
            len(valid),
            [v["action_def"].get("function") for v in valid],
        )
        await self.executor.replace(valid)


def load_prompt_bundle(prompts_dir: str | Path) -> dict[str, str]:
    root = Path(prompts_dir)
    return {
        "identity": load_text(root / "identity.md"),
        "env_template": load_text(root / "env_template.md"),
        "action_prompt": load_text(root / "action_prompt.md"),
    }
