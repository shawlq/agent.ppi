# Runtime Debug UI

独立于 `tests/console` 的 runtime 调试页：连接 agent → 启动 ThinkLoop → 7 面板观察 Cam/DF/VLM/Context/Prompt/LLM/Actions。

## 依赖

```bash
pip install -r requirements.txt
# runtime / sim_agent 另需 httpx（见 src/runtime/requirements.txt）
```

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
