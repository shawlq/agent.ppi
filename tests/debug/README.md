# Runtime Debug UI

独立于 `tests/console` 的 runtime 调试页：连接 agent → 启动 ThinkLoop → 按 `DebugHub` 下发的 `panels` 裸显示各字段。

布局为 Webviz 风格 mosaic：全新打开默认 2×2（`cam` / `df` / `vlm` / `actions_valid`）；每个面板标题栏 ⋮ 菜单支持 Split Vertical / Split Horizontal / Close / Select。Select 列表来自当前 snapshot 的 `panels` keys。布局树保存在 `localStorage`（`debug.board.mosaic.v3`），刷新后恢复。

## 快照协议

SSE / `GET /api/debug/latest` 载荷形如：

```json
{
  "kind": "round",
  "stamp": 0,
  "round_id": 1,
  "panels": {
    "cam":  { "type": "image", "rev": 3, "src": "/api/debug/image/cam" },
    "vlm":  { "type": "json",  "value": {} },
    "prompt": { "type": "text", "value": "..." }
  }
}
```

- UI **只按 `type` 渲染**（`text` | `json` | `image`），不做业务字段组合。
- Runtime 增删 `panels` key 后，Select 菜单自动出现；无需改前端。
- 稀疏 `cam` 事件只带 `panels.cam`；前端浅合并，其它面板内容保留。

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
- `GET /api/debug/latest`
- `GET /api/debug/image/{name}`（与 panel 名一致，如 `cam` / `df`）

## 冒烟检查

1. 连接后 Cam 随相机 `rev` 刷新；文本面板不因 cam 事件被清空。
2. 每轮 think 后出现 `df` / `vlm` / `prompt` / `llm` / `reason` / `actions_valid` 等 panel。
3. ⋮ → Select 列出 snapshot 中全部 panel keys；切换后按 type 显示。
