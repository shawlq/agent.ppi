# PuppyPi Web Console

主机侧 Web 控制台：右上角加载 `src/agents/*_agent`，读取 proxy 动作表，经 agent client 下发指令。

## 启动

```bash
cd tests/console
pip install -r requirements.txt
./service.sh
```

浏览器：<http://127.0.0.1:8768/>

## 无真机验收（推荐）

1. 另开终端启动仿真：`cd tests/sim && ./service.sh`（:8765）
2. 打开 console 与 sim 两个页面
3. Console 右上角选择 `sim_agent` → **加载**
4. 下拉选择动作 → `+` 入队
5. Console 状态显示成功；sim 页面同步播放动画

## 真机（ppi_agent）

```bash
CONSOLE_MODE=ros ./service.sh
# 或 mock：CONSOLE_MODE=mock ./service.sh
```

加载 `ppi_agent` 后连接机器人 IP。proxy 见 [`src/agents/ppi_agent/proxy/proxy.json`](../../src/agents/ppi_agent/proxy/proxy.json)。

## 操作

| 操作 | 说明 |
|------|------|
| 右上角加载 Agent | 列举 `src/agents/*_agent`，读取 `proxy/proxy.json`（含 ip）并自动连接 |
| 指令列表 `+` / 双击 | 加入队列；列表底部可拖拽改高度 |
| 错误气泡 | proxy JSON / client 脚本异常、按 ip 连接失败时弹出详细信息 |

## API

- `GET /api/agents` — 可用 agent 列表
- `POST /api/agents/load` — `{ "name": "sim_agent" }`
- `GET /api/actions` — 当前已加载动作表
- `GET /api/robot` / `GET /api/health`
- `POST /api/connect` — `{ "host" }`
- `POST /api/action/run` — `{ "function", "params" }`
- `GET /api/camera/stream` — ppi MJPEG 代理；sim/未加载返回占位图

环境变量：`CONSOLE_MODE=ros|mock`、`CONSOLE_AGENT=sim_agent`（可选启动即加载）、`HOST`、`PORT`。
