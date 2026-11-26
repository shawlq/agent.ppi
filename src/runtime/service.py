"""In-process RuntimeService for debug UI / embedding hosts."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from .agent_loader import create_agent_client
from .context import RuntimeContext
from .debug import DebugHub
from .executor import ActionExecutor
from .inbox import MessageInbox
from .loop import ThinkLoop, load_prompt_bundle
from .models.factory import create_llm, create_vlm, load_models_config

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def load_runtime_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = _resolve(path or "src/runtime/configs/runtime.json")
    with cfg_path.open(encoding="utf-8") as f:
        return json.load(f)


class RuntimeService:
    """Own inbox/loop/executor/debug hub; optionally own the agent client."""

    def __init__(self) -> None:
        self.debug_hub = DebugHub(history_rounds=3)
        self.running = False
        self.agent_name: str | None = None
        self.client: Any | None = None
        self.proxy: dict[str, Any] | None = None
        self._owns_client = False
        self._inbox: MessageInbox | None = None
        self._executor: ActionExecutor | None = None
        self._loop: ThinkLoop | None = None
        self._cam_task: asyncio.Task[None] | None = None
        self._cfg: dict[str, Any] = {}

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "agent": self.agent_name,
            "owns_client": self._owns_client,
            "rounds": self._loop.rounds_done if self._loop else 0,
            "cam_rev": self.debug_hub.cam_rev,
            "df_rev": self.debug_hub.df_rev,
            "latest_round": (self.debug_hub.latest() or {}).get("round_id"),
        }

    async def start(
        self,
        *,
        agent_name: str = "sim_agent",
        client_mode: str | None = None,
        proxy: dict[str, Any] | None = None,
        client: Any | None = None,
        runtime_config: dict[str, Any] | None = None,
        models_config: dict[str, Any] | None = None,
        max_rounds: int | None = None,
    ) -> dict[str, Any]:
        if self.running:
            await self.stop()

        cfg = dict(runtime_config or load_runtime_config())
        self._cfg = cfg
        self.agent_name = agent_name

        if client is not None and proxy is not None:
            self.client = client
            self.proxy = proxy
            self._owns_client = False
        else:
            mode = client_mode
            if mode is None:
                mode = cfg.get("client_mode") or (
                    "sim" if agent_name == "sim_agent" else "ros"
                )
            self.proxy, self.client = create_agent_client(agent_name, mode)
            self._owns_client = True
            await self.client.connect()

        prompts_dir = _resolve(cfg.get("prompts_dir") or "src/runtime/prompts")
        prompts = load_prompt_bundle(prompts_dir)
        frame_path = _resolve(cfg.get("frame_path") or "src/runtime/data/latest_frame.jpg")

        if models_config is None:
            models_cfg_path = _resolve(
                cfg.get("models_config") or "src/runtime/configs/models.json"
            )
            models_config = load_models_config(models_cfg_path)

        inbox = MessageInbox(frame_path=frame_path)
        context = RuntimeContext(
            proxy=self.proxy or {},
            identity_text=prompts["identity"],
            history_maxlen=int(cfg.get("history_maxlen") or 20),
        )
        executor = ActionExecutor(self.client, context)
        vlm = create_vlm(models_config.get("vlm") or {"mode": "mock"})
        llm = create_llm(models_config.get("llm") or {"mode": "mock"})
        loop = ThinkLoop(
            inbox=inbox,
            context=context,
            executor=executor,
            vlm=vlm,
            llm=llm,
            env_template=prompts["env_template"],
            action_template=prompts["action_prompt"],
            think_hz=float(cfg.get("think_hz") or 0.2),
            min_actions=int(cfg.get("min_actions") or 3),
            max_actions=int(cfg.get("max_actions") or 5),
            max_rounds=max_rounds,
            debug_hub=self.debug_hub,
        )

        self._inbox = inbox
        self._executor = executor
        self._loop = loop

        # Bridge client image callbacks → inbox + debug cam.
        def _on_image(modality: str, msg: dict[str, Any]) -> None:
            inbox.on_message(modality, msg)
            if modality == "image":
                data = msg.get("data")
                if isinstance(data, (bytes, bytearray)):
                    self.debug_hub.update_cam(bytes(data), emit=True)

        poll_hz = float(cfg.get("image_poll_hz") or 2.0)
        if not hasattr(self.client, "subscribe_message"):
            raise RuntimeError("agent client missing subscribe_message()")
        await self.client.subscribe_message("image", _on_image, poll_hz=poll_hz)

        for _ in range(40):
            if inbox.has_image():
                break
            await asyncio.sleep(0.05)

        executor.start()
        loop.start()
        self.running = True
        logger.info("RuntimeService started agent=%s", agent_name)
        return self.status()

    async def stop(self) -> None:
        self.running = False
        if self._loop is not None:
            await self._loop.stop()
            self._loop = None
        if self._executor is not None:
            await self._executor.close()
            self._executor = None
        if self.client is not None:
            try:
                if hasattr(self.client, "unsubscribe_message"):
                    await self.client.unsubscribe_message("image")
            except Exception:
                logger.exception("unsubscribe failed")
            if self._owns_client:
                try:
                    await self.client.close()
                except Exception:
                    logger.exception("client close failed")
                self.client = None
                self.proxy = None
        self._inbox = None
        self.agent_name = None
        logger.info("RuntimeService stopped")
