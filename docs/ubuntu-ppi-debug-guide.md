# Ubuntu 上 PuppyPi 接口调试环境指南

本机为 **Ubuntu**。目标：完成 **连上 PPI → 进入 Docker → 验收相机/动作**，对应 [roadmap-zero-to-one.md](roadmap-zero-to-one.md) 的 Phase 1。官方安装截图多为 Windows，下文给出 Ubuntu 等价步骤，并附官方链接。

整体架构设计见 [design.md](design.md)。

---

## 0. 凭证与官方入口

| 项 | 默认值 |
|----|--------|
| AP 热点名 | `HW-` 开头 |
| AP 热点密码 | `hiwonder` |
| AP 固定 IP | `192.168.149.1` |
| SSH/VNC 用户 | `pi` |
| SSH/VNC 密码 | `raspberrypi`（Pi5；个别旧文档写 `raspberry`） |

- 文档首页：[PuppyPi Documentation](https://docs.hiwonder.com/projects/PuppyPi/en/latest/index.html)
- 远程连接 / Docker / 网络（必读）：[3. Remote Tool Installation and Docker Entry Method](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)
- 中文通用连机：[【通用】树莓派系列产品远程连接教程](https://forum.hiwonder.com.cn/t/topic/662)
- Wiki 镜像（同章）：[wiki.hiwonder.com · 第 3 章](https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)

---

## 1. Ubuntu 主机准备

台式机需 **支持 5G 的无线网卡**（官方要求；可用 USB 无线网卡）。

```bash
sudo apt update
sudo apt install -y openssh-client net-tools nmap curl wget

# VNC：推荐 RealVNC Viewer（与官方工具一致）
# 从 RealVNC 官网下载 Linux .deb 后：
#   sudo apt install ./VNC-Viewer-*-Linux-x64.deb

# 备选：Remmina
sudo apt install -y remmina remmina-plugin-vnc
```

---

## 2. 开机与 AP 直连（第一次必做）

官方步骤：[3.1 VNC Installation and Connection](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)。

### 2.1 开机

1. 将 PuppyPi **卧姿**放在平面上再上电。
2. 扩展板 **LED1 闪烁** + **蜂鸣一声**，表示启动成功。

### 2.2 连接热点

```bash
nmcli device wifi list
nmcli device wifi connect "HW-xxxx" password "hiwonder"   # 将 HW-xxxx 换成实际热点名
ping -c 3 192.168.149.1
```

### 2.3 VNC 图形桌面

1. 打开 RealVNC Viewer 或 Remmina（VNC）。
2. 地址：`192.168.149.1`
3. 用户：`pi`，密码：`raspberrypi`
4. 若黑屏或只剩光标，重启机器狗后再连。

### 2.4 SSH 命令行

```bash
ssh pi@192.168.149.1
# 密码：raspberrypi
```

---

## 3. 进入功能 Docker

业务程序与源码在 **Docker 容器**内，不在树莓派宿主机家目录直接跑完所有功能。官方：[3.2 / 3.3 Docker](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)。

在 VNC 终端或已登录的 SSH 中：

```bash
# 宿主机家目录可见
ls
# 常见：puppypi/、hiwonder-toolbox/

docker ps -a
```

进入容器（`<id>` 换成 `docker ps -a` 里的容器 ID，或官方示例名 `puppypi`）：

```bash
docker exec -it -u ubuntu -w /home/ubuntu <id> /bin/bash

# 官方便捷写法之一：
# xhost + && docker exec -it -u ubuntu -w /home/ubuntu puppypi /bin/zsh
```

容器内：

```bash
ls
# 关注：puppypi/（ROS 工作空间）、share/

cd puppypi/src
ls
# 常见包：puppy_control、puppy_standard_functions、puppy_advanced_functions 等
```

退出容器但保持运行：`Ctrl+P` 再 `Ctrl+Q`。输入 `exit` 可能停掉容器，按官方说明慎用。

---

## 4. 切 STA 局域网（与 Ubuntu / Spark 同网，推荐开发）

AP 模式下 PC 挂在狗的热点上，通常 **无外网**，也不便与 DGX Spark 同网。开发请切 **STA（局域网）**。

官方：[3.5 Network Configuration](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)、[3.6 Connecting in LAN Mode](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)。

### 4.1 用配置文件切换（在已 AP 连上的 VNC/SSH 里操作）

```bash
cd ~/hiwonder-toolbox    # 树莓派宿主机侧路径，以实机为准
vim wifi_conf.py
```

修改要点：

- `HW_WIFI_MODE = 2`（`1` = AP，`2` = STA）
- 填写 `HW_WIFI_STA_SSID`、`HW_WIFI_STA_PASSWORD`（建议 5G SSID，吞吐更好）

保存后重启 Wi‑Fi 服务：

```bash
sudo systemctl restart wifi.service
# 部分机型文档写 hw_wifi.service，以板端实际为准：
# systemctl list-units '*wifi*'
```

切换后 AP 热点会消失；Ubuntu 改连 **同一路由器**，再查狗的局域网 IP。

### 4.2 查 IP 并重连

- WonderPi APP：长按设备图标看 IP（需手机与狗同网）。
- 路由器管理页查 DHCP 客户端。
- 同网扫描（示例）：

```bash
nmap -sn 192.168.1.0/24    # 网段按你的路由器修改
ssh pi@<LAN_IP>
```

### 4.3 退回 AP

扩展板 **长按 KEY1**，直到蓝灯变为约一秒一闪，重新搜索 `HW-` 热点。官方 3.6.1。

也可用 APP「局域网模式」配置，见同一章节；配置文件方式不依赖手机。

---

## 5. 接口调试验收

把实测结果记到 [bringup.md](bringup.md)（若尚未创建可新建）：LAN IP、容器名、分辨率、已验证动作名。

### 5.1 动作接口

**方式 A — 桌面 PC 软件（最快确认执行链路）**

1. VNC 进桌面，打开 **PuppyPi PC Software**。
2. Open Action File / 下拉选动作组 → Run。
3. 官方教程：[5. ROS1 PC Software Action Control Courses](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/5.ROS1_PC%20Software_Action_Control_Courses.html)
4. 动作组路径提示：`/home/ubuntu/software/puppypi_control/ActionGroups`

**方式 B — 容器内 ROS / 脚本**

1. 进入 Docker（第 3 节）。
2. 按官方课程启动 `puppy_control` 等相关节点，触发站立 / 坐下 / 短距前进 / 停止。
3. 将实际可调用的指令名记入后续 `configs/action_whitelist.yaml`。

**验收**：至少 3 个动作可远程触发；知道如何停止或回安全姿态。

### 5.2 相机

1. 官方视觉课：[7. ROS1 AI Vision and Tracking Course](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/7.ROS1_AI_Vision_and_Tracking_Course.html)
2. 在 VNC 下跑官方视觉 demo，确认有画面。
3. 或在容器内按文档启动相机 launch / 查看图像 topic。

**验收**：稳定出图；记下分辨率与大致延迟，写入 bringup 记录。主机侧「收 JPEG ≥30s」脚本可在 Phase 1 联调时再写到 `scripts/bringup/`。

### 5.3 麦克风

若官方无独立「mic → PC」章节：先在板端确认录音设备存在；与主机互通可后置。**不阻塞**视觉-动作闭环（见 roadmap）。

### 5.4 ROS1 / ROS2

- 桌面 **版本配置工具** 可切换；默认多为 ROS1。
- 官方：[3.4 ROS Version Switch Tool Guide](https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html)
- 第一期建议跟官方默认，除非项目已明确 ROS2。

---

## 6. Phase 1 检查清单

- [ ] AP 下 VNC 能进桌面
- [ ] AP 下 `ssh pi@192.168.149.1` 成功
- [ ] `docker ps -a` 正常，能 `exec` 进容器并看到 `puppypi/src`
- [ ] 已切 STA，Ubuntu 与 PPI 同网，可用局域网 IP SSH/VNC
- [ ] 至少 3 个动作可触发，有停止/安全姿态办法
- [ ] 相机有稳定画面（分辨率/延迟已记录）
- [ ] （可选）mic 通路结论已记下

全部勾选后，进入 [roadmap-zero-to-one.md](roadmap-zero-to-one.md) Phase 2（ppi runtime）。

---

## 7. 官方链接汇总

| 主题 | 链接 |
|------|------|
| 文档首页 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/index.html |
| 远程工具 / Docker / AP·STA | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html |
| 同上（wiki） | https://wiki.hiwonder.com/projects/PuppyPi/en/latest/docs/3.Remote_Tool_Installation_Connection.html |
| 中文远程连接 | https://forum.hiwonder.com.cn/t/topic/662 |
| PC 软件动作编辑 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/5.ROS1_PC%20Software_Action_Control_Courses.html |
| AI 视觉与跟踪 | https://docs.hiwonder.com/projects/PuppyPi/en/latest/docs/7.ROS1_AI_Vision_and_Tracking_Course.html |
