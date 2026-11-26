"""Run: python -m src.runtime [--agent sim_agent] [--config ...] [--rounds N]"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow `python -m src.runtime` from repo root without install.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.runtime.agent_loader import create_agent_client  # noqa: E402
from src.runtime.context import RuntimeContext  # noqa: E402
from src.runtime.executor import ActionExecutor  # noqa: E402
from src.runtime.inbox import MessageInbox  # noqa: E402
from src.runtime.loop import ThinkLoop, load_prompt_bundle  # noqa: E402
from src.runtime.models.factory import create_llm, create_vlm, load_models_config  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("runtime")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def load_runtime_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


async def main_async(args: argparse.Namespace) -> int:
    cfg_path = _resolve(args.config)
    cfg = load_runtime_config(cfg_path)

    agent_name = args.agent or cfg.get("agent_name") or "sim_agent"
    client_mode = args.mode or cfg.get("client_mode")
    if args.mock_client:
        client_mode = "mock"

    prompts_dir = _resolve(cfg.get("prompts_dir") or "src/runtime/prompts")
    models_cfg_path = _resolve(cfg.get("models_config") or "src/runtime/configs/models.json")
    frame_path = _resolve(cfg.get("frame_path") or "src/runtime/data/latest_frame.jpg")

    if args.openai:
        # Force openai mode for both while keeping endpoints from file.
        models_cfg = load_models_config(models_cfg_path)
        for key in ("vlm", "llm"):
            models_cfg.setdefault(key, {})
            models_cfg[key]["mode"] = "openai"
    else:
        models_cfg = load_models_config(models_cfg_path)

    prompts = load_prompt_bundle(prompts_dir)
    proxy, client = create_agent_client(agent_name, client_mode)

    inbox = MessageInbox(frame_path=frame_path)
    context = RuntimeContext(
        proxy=proxy,
        identity_text=prompts["identity"],
        history_maxlen=int(cfg.get("history_maxlen") or 20),
    )
    executor = ActionExecutor(client, context)
    vlm = create_vlm(models_cfg.get("vlm") or {"mode": "mock"})
    llm = create_llm(models_cfg.get("llm") or {"mode": "mock"})

    think_hz = float(args.hz if args.hz is not None else cfg.get("think_hz") or 0.2)
    loop = ThinkLoop(
        inbox=inbox,
        context=context,
        executor=executor,
        vlm=vlm,
        llm=llm,
        env_template=prompts["env_template"],
        action_template=prompts["action_prompt"],
        think_hz=think_hz,
        min_actions=int(cfg.get("min_actions") or 3),
        max_actions=int(cfg.get("max_actions") or 5),
        max_rounds=args.rounds,
    )

    await client.connect()
    poll_hz = float(cfg.get("image_poll_hz") or 2.0)
    if hasattr(client, "subscribe_message"):
        await client.subscribe_message(
            "image", inbox.on_message, poll_hz=poll_hz
        )
    else:
        raise RuntimeError(
            f"{agent_name} client missing subscribe_message(); "
            "update agent client.py"
        )

    # Yield so the client subscribe task can deliver the first frame.
    for _ in range(50):
        if inbox.has_image():
            break
        await asyncio.sleep(0.05)
    if not inbox.has_image():
        logger.warning("no image received before think loop; rounds may skip")

    executor.start()
    try:
        await loop.run()
    finally:
        await loop.stop()
        await executor.close()
        if hasattr(client, "unsubscribe_message"):
            await client.unsubscribe_message("image")
        await client.close()
        logger.info(
            "shutdown history=%d rounds=%d",
            len(context.history()),
            loop.rounds_done,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Embodied continuous-thinking runtime")
    p.add_argument(
        "--config",
        default="src/runtime/configs/runtime.json",
        help="runtime.json path",
    )
    p.add_argument("--agent", default=None, help="agent folder name under src/agents/")
    p.add_argument("--mode", default=None, help="create_client mode (sim|ros|mock)")
    p.add_argument(
        "--mock-client",
        action="store_true",
        help="force client_mode=mock (ppi MockClient or sim if supported)",
    )
    p.add_argument("--hz", type=float, default=None, help="think frequency Hz")
    p.add_argument("--rounds", type=int, default=None, help="stop after N think rounds")
    p.add_argument(
        "--openai",
        action="store_true",
        help="force VLM/LLM mode=openai using models.json endpoints",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    try:
        raise SystemExit(asyncio.run(main_async(args)))
    except KeyboardInterrupt:
        logger.info("interrupted")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
