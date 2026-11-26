# PuppyPi 家庭场景 3D Web 仿真

Python FastAPI 托管页面，Three.js 渲染客厅场景与机器狗。可接收 console/`sim_agent` 经 ROS 形接口投递的命令。

## 启动

```bash
cd tests/sim
pip install -r requirements.txt
./service.sh          # 后台 :8765
```

浏览器：<http://127.0.0.1:8765/>

Three.js 已本地化到 `static/vendor/three@0.160.0/`（不依赖外网 CDN）。若仍无画面，打开开发者工具看 hint 条/`three.module.js` 是否 200，并确认 WebGL 未禁用。

## 与 Console 联调

不依赖真机、不依赖系统 rosbridge：

1. 启动本服务
2. 启动 `tests/console`，加载 `sim_agent`
3. Console 执行动作 → `POST /api/ros/command`（topic `/sim_dog/command`）→ 本页 WebSocket `/ws/commands` → `RobotDog.play`

动作表优先读 [`src/agents/sim_agent/proxy/proxy.json`](../../src/agents/sim_agent/proxy/proxy.json)。

## API

- `GET /api/health` — 健康检查（sim_agent connect 依赖）
- `POST /api/ros/command` — `{ "topic": "/sim_dog/command", "data": { "function", "params", "cost_time_sec" } }`
- `WS /ws/commands` — 向前端推送命令
- `GET /api/scene` / `/api/actions` / `/api/ui`

## 本地面板

右侧指令列表仍可手动入队，用于单独调试动画。
