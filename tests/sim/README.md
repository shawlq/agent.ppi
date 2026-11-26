# PuppyPi 家庭场景 3D Web 仿真

Python FastAPI 托管页面，Three.js 渲染客厅场景与机器狗。可接收 console/`sim_agent` 经 ROS 形接口投递的命令，并发布头载前向相机图像。

## 启动

```bash
cd tests/sim
pip install -r requirements.txt
./service.sh          # 后台 :8765
```

浏览器：<http://127.0.0.1:8765/>

**头载相机依赖本页保持打开**：页面内以约 10Hz 从机器狗头部渲染前方 3D 环境，上传到网关后供 Console 显示。关闭仿真页后图像会过期。

Three.js 已本地化到 `static/vendor/three@0.160.0/`（不依赖外网 CDN）。若仍无画面，打开开发者工具看 hint 条/`three.module.js` 是否 200，并确认 WebGL 未禁用。

## 与 Console 联调

不依赖真机、不依赖系统 rosbridge：

1. 启动本服务
2. **打开**本页（生成 `/sim_dog/image_raw` 图像流）
3. 启动 `tests/console`，加载 `sim_agent`
4. Console 摄像头区应显示头载前向画面
5. Console 执行动作 → `POST /api/ros/command`（topic `/sim_dog/command`）→ 本页 WebSocket `/ws/commands` → `RobotDog.play`；画面随前进/转向/站立/趴下等姿态变化

动作表优先读 [`src/agents/sim_agent/proxy/proxy.json`](../../src/agents/sim_agent/proxy/proxy.json)。

## API

- `GET /api/health` — 健康检查（含 `image_ok` / `image_topic`）
- `POST /api/ros/command` — `{ "topic": "/sim_dog/command", "data": { "function", "params", "cost_time_sec" } }`
- `POST /api/ros/image` — multipart：`topic`、`encoding=jpeg`、`width`、`height`、`frame`（浏览器头载相机上传）
- `GET /stream?topic=/sim_dog/image_raw` — web_video_server 兼容 MJPEG
- `GET /snapshot?topic=/sim_dog/image_raw` — 单帧 JPEG
- `WS /ws/commands` — 向前端推送命令
- `GET /api/scene` / `/api/actions` / `/api/ui`

头载相机参数见 `configs/ui.json` 的 `head_camera`（分辨率、FOV、JPEG 质量、Hz）。

## 本地面板

右侧指令列表仍可手动入队，用于单独调试动画。
