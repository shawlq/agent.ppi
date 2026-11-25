# PuppyPi Console · ROS / Action 接口文档

本文档描述 [`tests/console/`](../tests/console/) Web Console 对接真机时使用的 **ROS 接口**、**动作指令表**，以及 Console HTTP API。真机联调默认地址以 [`tests/console/configs/robot.json`](../tests/console/configs/robot.json) 为准（当前 `192.168.1.9`）。

> **版本说明**：联调设备 Docker `puppypi` 内实测为 **ROS1 Noetic**（`rosmaster` + `rosbridge_websocket`）。控制面（Topic / Service 名与字段）与幻尔手册 ROS2 章节中的 `puppy_control` 接口同类；消息类型在 ROS1 下为 `puppy_control/*`，ROS2 源码树中多为 `puppy_control_msgs/*`。

---

## 1. ROS 接口总览

### 1.1 桥接与图像服务（设备侧已自启）

| 组件 | 地址 | 说明 |
|------|------|------|
| `web_video_server` | `http://{robot_host}:8080` | 将图像 Topic 以 MJPEG 提供给浏览器 |
| `rosbridge_websocket` | `ws://{robot_host}:9090` | Console 经 `roslibpy` 调用 Service / 发布 Topic |
| 动作组文件目录 | `/home/ubuntu/software/puppypi_control/ActionGroups/` | `*.d6ac` / `*.d6a` |

浏览器直连图像示例：

```text
http://192.168.1.9:8080/stream?topic=/usb_cam/image_raw
http://192.168.1.9:8080/snapshot?topic=/usb_cam/image_raw
```

### 1.2 Topic

| Topic | 方向 | 消息类型（ROS1 实测） | 用途 |
|-------|------|----------------------|------|
| `/usb_cam/image_raw` | 设备 → 订阅方 | `sensor_msgs/Image` | 摄像头原始图；经 `web_video_server` 出流 |
| `/usb_cam/image_raw/compressed` | 设备 → 订阅方 | `sensor_msgs/CompressedImage` | 压缩图（Console 当前未用） |
| `/puppy_control/velocity` | Console → 设备 | `puppy_control/Velocity` | 步态速度：前进 / 后退 / 转向 |
| `/puppy_control/pose` | （可选）→ 设备 | `puppy_control/Pose` | 姿态（Console 当前未用） |
| `/puppy_control/gait` | （可选）→ 设备 | `puppy_control/Gait` | 步态参数（Console 当前未用） |

#### `puppy_control/Velocity`

```text
float32 x          # 前后速度（正：前进，负：后退）
float32 y
float32 yaw_rate   # 偏航角速度（rad/s）
```

Console 内部以「度/秒」配置，下发前转换为弧度：`yaw_rate = radians(yaw_rate_deg)`。

#### `puppy_control/Pose`（参考，未接入 Console）

```text
float32 roll
float32 pitch
float32 yaw
float32 height
float32 x_shift
float32 stance_x
float32 stance_y
int32   run_time
```

### 1.3 Service

| Service | 类型（ROS1 实测） | 用途 |
|---------|-------------------|------|
| `/puppy_control/runActionGroup` | `puppy_control/SetRunActionName` | 执行动作组文件（`*.d6ac`） |
| `/puppy_control/go_home` | `std_srvs/Empty` | 回初始（官方大模型示例用；Console 未用） |

#### `puppy_control/SetRunActionName`

**Request**

```text
string name    # 动作组文件名，如 "stand.d6ac"
bool   wait    # true：阻塞至动作组结束
```

**Response**

```text
bool   success
string message
```

Console 调用约定：

- `name = "{ros_name}.d6ac"`
- `wait = true`

### 1.4 Console → 真机调用链

```text
Browser
  ├─ <img>  GET /api/camera/stream
  │            └─ proxy → http://{host}:8080/stream?topic=/usb_cam/image_raw
  └─ POST /api/action/run
             └─ roslibpy → ws://{host}:9090
                    ├─ action_group → /puppy_control/runActionGroup
                    └─ velocity     → /puppy_control/velocity
```

配置项见 [`tests/console/configs/robot.json`](../tests/console/configs/robot.json)：

| 字段 | 含义 | 默认 |
|------|------|------|
| `robot_host` | 设备 IP | `192.168.1.9` |
| `web_video_port` | 视频端口 | `8080` |
| `rosbridge_port` | rosbridge 端口 | `9090` |
| `image_topic` | 图像 Topic | `/usb_cam/image_raw` |
| `run_action_service` | 动作服务名 | `/puppy_control/runActionGroup` |
| `velocity_topic` | 速度 Topic | `/puppy_control/velocity` |
| `run_action_type` | 服务类型 | `puppy_control/SetRunActionName` |
| `velocity_type` | 消息类型 | `puppy_control/Velocity` |

---

## 2. Action 接口文档

动作表来源对齐官方仓库 [`large_models/action.py`](https://github.com/Hiwonder/PuppyPi-ROS/blob/ros2/large_models/large_models/action.py)，配置文件：[`tests/console/configs/actions.json`](../tests/console/configs/actions.json)。共 **18** 项。

### 2.1 字段说明

| 字段 | 说明 |
|------|------|
| `action` | UI 显示名（中文） |
| `function` | Console / Agent 逻辑名；`POST /api/action/run` 的 `function` |
| `kind` | `action_group`：调 `runActionGroup`；`velocity`：发 `/puppy_control/velocity` |
| `ros_name` | 仅 `action_group`：动作组基名（不含扩展名） |
| `cost_time_sec` | 参考耗时；`velocity` 默认运动时长（秒） |
| `velocity` | 仅 `velocity`：`x` / `y` / `yaw_rate_deg` |
| `params` | UI 可编辑参数元数据 |

### 2.2 HTTP 执行接口

`POST /api/action/run`

**Request**

```json
{
  "function": "stand",
  "params": {}
}
```

带角度示例（左转 90°）：

```json
{
  "function": "turn_left",
  "params": { "angle_deg": 90 }
}
```

**Response（动作组）**

```json
{
  "ok": true,
  "mode": "ros",
  "kind": "action_group",
  "name": "stand.d6ac",
  "result": { "success": true, "message": "stand.d6ac" }
}
```

**Response（速度）**

```json
{
  "ok": true,
  "mode": "ros",
  "kind": "velocity",
  "function": "forward",
  "velocity": { "x": 5.0, "y": 0.0, "yaw_rate_deg": 0.0 },
  "duration_sec": 2.0
}
```

### 2.3 执行语义

#### `kind = action_group`

1. 组装 `name = "{ros_name}.d6ac"`
2. 调用 `/puppy_control/runActionGroup`，`wait=true`
3. 以响应 `success` 作为 `ok`

#### `kind = velocity`

1. 发布 `Velocity{x, y, yaw_rate}`（`yaw_rate` 为弧度）
2. 等待 `duration_sec` 后发布全零速度停下
3. 若 `params.angle_deg` 存在且 `|yaw_rate_deg| > 0`：  
   `duration_sec = max(0.2, |angle_deg| / |yaw_rate_deg|)`  
   （默认 90°、30°/s → 约 3s）

#### 左右转极性（真机实测）

| function | `yaw_rate_deg` | 说明 |
|----------|----------------|------|
| `turn_left` | `+30` | 点击「左转」应对应机体左转 |
| `turn_right` | `-30` | 与官方部分示例符号相反，以真机为准 |

### 2.4 动作一览

#### ActionGroup（14）

| 显示名 | function | ros_name → 文件 | cost_time_sec |
|--------|----------|-----------------|---------------|
| 站立 | `stand` | `stand.d6ac` | 1.5 |
| 坐下 | `sit` | `sit.d6ac` | 2.0 |
| 拳击 | `boxing` | `boxing.d6ac` | 5.0 |
| 俯卧撑 | `push_up` | `push-up01.d6ac` | 8.0 |
| 握手 | `shake_hands` | `shake_hands.d6ac` | 4.0 |
| 单手握手 | `shake_hand` | `shake_hand.d6ac` | 4.0 |
| 点头 | `nod` | `nod.d6ac` | 2.0 |
| 招手 | `wave` | `wave.d6ac` | 3.0 |
| 左脚踢球 | `kick_ball_left` | `kick_ball_left.d6ac` | 3.0 |
| 右脚踢球 | `kick_ball_right` | `kick_ball_right.d6ac` | 3.0 |
| 太空步 | `moonwalk` | `moonwalk.d6ac` | 8.0 |
| 趴下 | `lie_down` | `lie_down.d6ac` | 2.0 |
| 伸懒腰 | `temp` | `temp.d6ac` | 4.0 |
| 鞠躬 | `bow` | `bow.d6ac` | 3.0 |

#### Velocity（4）

| 显示名 | function | x | yaw_rate_deg | 默认时长 | 参数 |
|--------|----------|---|--------------|----------|------|
| 前进一步 | `forward` | `5.0` | `0` | 2.0s | — |
| 后退一步 | `back` | `-5.0` | `0` | 2.0s | — |
| 左转 | `turn_left` | `-5.0` | `+30` | 由角度推算 | `angle_deg`（默认 90） |
| 右转 | `turn_right` | `-5.0` | `-30` | 由角度推算 | `angle_deg`（默认 90） |

### 2.5 未纳入 Console 的官方能力

以下在官方 `action.py` / `function_call.py` 中存在，但为**长时 demo 进程**，未放入队列：

| 能力 | 说明 |
|------|------|
| `kick_ball(color)` | `ros2 run example kick_ball_demo` / 对应 ROS1 demo |
| `visual_patrol(color)` | 视觉巡线 demo |

---

## 3. Console HTTP API（附属）

默认监听 `http://0.0.0.0:8767`。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/` | Web 页面 |
| `GET` | `/api/actions` | 返回 `actions.json` |
| `GET` | `/api/robot` | 当前连接配置 + `mode` |
| `POST` | `/api/connect` | `{"host":"192.168.1.9"}` 切换 IP 并重连 rosbridge |
| `GET` | `/api/health` | rosbridge / 视频可达性 |
| `GET` | `/api/camera/stream` | 代理设备 MJPEG（`CONSOLE_MODE=mock` 时为占位图） |
| `POST` | `/api/action/run` | 见 §2.2 |

环境变量：`CONSOLE_MODE=ros|mock`、`ROBOT_HOST`、`HOST`、`PORT`。

---

## 4. 官方文档链接

### 4.1 总入口

| 主题 | 链接 |
|------|------|
| PuppyPi 文档首页 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/index.html |
| Wiki 镜像 | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/index.html |
| 官方 ROS 源码（含 `large_models/action.py`） | https://github.com/Hiwonder/PuppyPi-ROS |

### 4.2 远程连接 / 环境

| 主题 | 链接 |
|------|------|
| 远程工具 / Docker / 网络 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html |
| 同上（wiki） | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html |
| 中文远程连接 | https://forum.hiwonder.com.cn/t/topic/662 |

### 4.3 运动控制 / 动作组 / 视觉

| 主题 | 链接 |
|------|------|
| ROS2 运动控制课程（含 Topic 通信、`web_video_server`、rosbridge 示例） | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/20.ROS2_Motion_Control_Course.html |
| ROS2 PC 软件动作编辑 / 动作组调用 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/21.ROS2_PC_Software_Action_Editing_Course.html |
| ROS1 PC 软件动作编辑 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/5.ROS1_PC%20Software_Action_Control_Courses.html |
| ROS2 AI 语音交互（含 `runActionGroup` / `moonwalk.d6ac` 示例） | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/28.ROS2_AI_Voice_Interaction_Courses.html |
| ROS1 AI 语音交互 | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/12.ROS1_AI_Voice_Interaction_Courses.html |
| ROS1 AI 视觉与跟踪 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/7.ROS1_AI_Vision_and_Tracking_Course.html |
| ROS2 机械臂课程（浏览器查看 `web_video_server` 画面） | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/33.ROS2_Robot_Arm_Course.html |

### 4.4 仓库内相关文档

| 文档 | 路径 |
|------|------|
| Ubuntu 联调指南 | [ubuntu-ppi-debug-guide.md](ubuntu-ppi-debug-guide.md) |
| 设计总览 | [design.md](design.md) |
| Bring-up 路线图 | [roadmap-zero-to-one.md](roadmap-zero-to-one.md) |
| Console 使用说明 | [../tests/console/README.md](../tests/console/README.md) |
