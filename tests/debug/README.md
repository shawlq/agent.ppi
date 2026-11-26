# Runtime Debug UI

独立于 `tests/console` 的 runtime 调试页：连接 agent → 启动 ThinkLoop → 观察 Cam/DF/VLM/Context/Prompt/LLM/Actions。

布局为 Webviz 风格 mosaic：全新打开默认 2×2（Cam / DF / VLM / Actions）；每个面板标题栏 ⋮ 菜单支持 Split Vertical / Split Horizontal / Close / Select。布局树保存在 `localStorage`（`debug.board.mosaic.v2`），刷新后恢复。文本面板仅在 `round` 快照时更新，相机帧不会清空内容。

## 依赖

```bash
# 在目标 conda/venv 中执行（例如 myenv）
pip install -r requirements.txt
```

`requirements.txt` 已包含 Debug UI 与 `src/runtime`（含 `httpx`）全部第三方依赖。

## 启动

```bash
# 1) Qwen3.6 OpenAI-compatible（默认 :8000）
# /home/atom/workdir/start_qwen36-35b-a3b-nvfp4.sh

# 2) 仿真出图（用 sim_agent 时）
../sim/service.sh start
# 浏览器打开仿真页，确保头载相机上传

# 3) Debug UI
./service.sh start
# http://127.0.0.1:8769/
```

默认选择 `sim_agent`，点「连接」即可。

## API 摘要

- `GET /api/agents`
- `POST /api/connect` `{ "agent": "sim_agent" }`
- `POST /api/disconnect`
- `GET /api/debug/stream`（SSE）
- `GET /api/debug/image/cam|df`
