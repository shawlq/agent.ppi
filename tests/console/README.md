# PuppyPi Web Console

主机侧 Web 控制台：显示官方摄像头流，右侧指令列表 + 执行队列（样式对齐 `tests/sim`）。动作指令对齐官方 [`large_models/action.py`](https://github.com/Hiwonder/PuppyPi-ROS/blob/ros2/large_models/large_models/action.py)（18 项）。

## 启动

```bash
cd tests/console
pip install -r requirements.txt

# 联真机（默认）
CONSOLE_MODE=ros ./service.sh

# 无真机时用 mock 跑 UI / 队列
CONSOLE_MODE=mock ./service.sh

# 覆盖 IP
ROBOT_HOST=192.168.1.9 CONSOLE_MODE=ros ./service.sh restart
```

浏览器打开：<http://127.0.0.1:8767/>（`HOST` / `PORT` 可覆盖，默认 `0.0.0.0:8767`）

## 真机前置（实测：192.168.1.9）

当前设备 Docker `puppypi` 内为 **ROS1 Noetic**（非 ROS2），但控制面与手册一致，上电后通常已自启：

| 服务 | 地址 |
|------|------|
| `web_video_server` | `http://192.168.1.9:8080` |
| `rosbridge_websocket` | `ws://192.168.1.9:9090` |
| 图像 Topic | `/usb_cam/image_raw` |
| 动作 Service | `/puppy_control/runActionGroup`（`puppy_control/SetRunActionName`） |
| 速度 Topic | `/puppy_control/velocity`（`puppy_control/Velocity`） |

直连验证图像：

```text
http://192.168.1.9:8080/stream?topic=/usb_cam/image_raw
```

若服务未起，在容器内（用户 `ubuntu`）启动官方 `web_video_server` / `rosbridge_websocket` 与 `puppy_control`。

配置见 [`configs/robot.json`](configs/robot.json)。**不要把 SSH 密码写入仓库。**

## 操作

| 操作 | 说明 |
|------|------|
| 指令列表 `+` | 加入队列；双击动作名也可入队 |
| 参数 / 次数 | 无参动作参数框禁用；次数默认 1 |
| 清空 | 丢弃尚未开始的排队项（正在执行的会跑完） |

## 接口映射

| Console | 真机官方接口 |
|---------|--------------|
| 摄像头 `/api/camera/stream` | `web_video_server` ← `/usb_cam/image_raw` |
| ActionGroup 动作 | `/puppy_control/runActionGroup`（`name=*.d6ac`, `wait=true`） |
| forward/back/turn_* | `/puppy_control/velocity` |

未纳入队列：`kick_ball(color)`、`visual_patrol(color)`（长期 demo）。

## API

- `GET /` — 页面
- `GET /api/actions` — 动作 JSON
- `GET /api/robot` — 机器人连接配置
- `GET /api/health` — rosbridge / 视频可达性
- `GET /api/camera/stream` — MJPEG 代理（mock 返回占位图）
- `POST /api/action/run` — `{ "function", "params" }` 执行单步

## 配置

| 文件 | 作用 |
|------|------|
| `configs/actions.json` | 官方对齐动作表 |
| `configs/robot.json` | host / 8080 / 9090 / topic / 消息类型 |

环境变量：`CONSOLE_MODE=ros|mock`、`ROBOT_HOST`、`HOST`、`PORT`。
