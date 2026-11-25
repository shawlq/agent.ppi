# PuppyPi 家庭场景 3D Web 仿真

Python FastAPI 托管页面，Three.js 渲染可 JSON 配置的客厅场景与机器狗；右上角支持焦点高度配置、指令列表与顺序执行队列。

## 启动

```bash
cd tests/sim
pip install -r requirements.txt
./service.sh          # 后台启动
# ./service.sh run    # 前台
# ./service.sh stop
# ./service.sh status
```

浏览器打开：<http://127.0.0.1:8765/>（可用 `HOST` / `PORT` 环境变量覆盖默认 `0.0.0.0:8765`）

## 操作

| 操作 | 说明 |
|------|------|
| 左键拖拽 | 绕焦点旋转视角 |
| 滚轮 | 缩放 |
| 双击地面 | 水平移动焦点（高度由右上角「焦点高度」决定，默认 1.7 m） |
| 指令列表 `+` | 加入队列；左转/右转可填角度，其余参数框禁用；次数默认 1 |
| 清空 | 丢弃尚未开始的排队项 |

碰撞：前进/后退/太空步时，正面撞墙或家具会停下；侧面擦碰会沿切向滑移并缓慢转向。半径与转向速率见 `configs/ui.json`。

## 配置文件

| 文件 | 作用 |
|------|------|
| `configs/scene_home.json` | 地板、墙、家具与机器狗初始位姿 |
| `configs/actions.json` | 动作表（名称、函数名、耗时、参数元数据） |
| `configs/ui.json` | 焦点高度、相机距离、步长等 UI 默认值 |

家具 `type` 支持：`sofa` / `chair` / `table` / `coffee_table` / `bench` / `tv` / `cabinet` / `tea_set`。

## API

- `GET /` — 页面
- `GET /api/scene` — 场景 JSON
- `GET /api/actions` — 动作 JSON
- `GET /api/ui` — UI JSON
