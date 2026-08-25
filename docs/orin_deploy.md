# Orin 部署机环境安装手册

> 用途: Orin 系统盘损坏/换机后的环境重建清单。按顺序执行, 每步带验证命令。
> 首次装机时边装边把 【待填】 项补全, 之后重装只需 30 分钟。
>
> 一键安装: `./scripts/install_orin_env.sh` (本文档的脚本化版本, 分步执行, 可选阶段)
>
> 最后更新: 2026-08-25 (依据工控机开发环境整理, Orin 实机尚未验证)

## 0. 系统刷机

Orin 只能刷 NVIDIA L4T 镜像 (底层即 Ubuntu 22.04), 不能装普通 Ubuntu ISO。

- 机型: 【待填: Orin NX / Nano / AGX】
- JetPack 版本: 【待填, 建议与工控机一致: JetPack 6.x + Ubuntu 22.04 + ROS2 Humble】
- 刷机方式: SDK Manager (Ubuntu 主机 + Orin recovery 模式), 组件可不装桌面全家桶
- 刷完第一件事: 检查启动顺序, 避免网络启动卡 2-3 分钟 (见 9.1)

验证:

```bash
cat /etc/nv_tegra_release        # L4T 版本
lsb_release -a                   # Ubuntu 22.04
```

## 1. 基础环境

### 1.1 ROS2 Humble + MoveIt

MoveIt 是必须的: `t1_moveit_config` 是双臂运动规划入口 (IK 插件
`cached_ik_kinematics_plugin/CachedKDLKinematicsPlugin` 由 `moveit_kinematics` 提供)。
开发机装的是 `ros-humble-moveit` 元包, 照搬即可。

```bash
sudo apt update
sudo apt install -y \
    ros-humble-desktop \
    ros-humble-moveit \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-controller-manager \
    ros-humble-joint-state-publisher \
    ros-humble-joint-state-publisher-gui \
    ros-humble-ros2launch \
    ros-humble-rosidl-generator-dds-idl \
    python3-colcon-common-extensions \
    python3-pip
```

说明:
- `robot_state_publisher` / `rviz2` / `xacro` 已含在 `ros-humble-desktop` 内
- `rosidl-default-generators` 已由 desktop -> ros-base -> ros-core 传递拉入,
  但 **`rosidl-generator-dds-idl` 不在任何元包依赖树里** (已验证全索引零反向依赖),
  编译接口包 (furance_interfaces / interface_pkg / control_interfaces) 时必需,
  必须显式安装, 漏了 colcon build 会报 IDL 生成器缺失
- `t1_moveit_config/package.xml` 声明了 `warehouse_ros_mongo`, 但开发机未装且
  运行正常 (生成模板的残留依赖), 无需安装
- 构建需要 cmake/gcc: JetPack 自带; 缺则 `sudo apt install -y build-essential cmake`

验证:

```bash
ros2 pkg list | grep -E "moveit_kinematics|moveit_ros_move_group|rmw_cyclonedds"   # 3 项都要有
dpkg -l ros-humble-rosidl-generator-dds-idl | tail -1                               # 状态应为 ii
```

### 1.2 DDS 配置 (多机通讯关键)

`~/.ros/cyclonedds_profile.xml`:

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<CycloneDDS xmlns="https://cdds.io/config">
    <Domain id="any">
        <General>
            <Interfaces>
                <NetworkInterface name="lo" />
            </Interfaces>
            <AllowMulticast>default</AllowMulticast>
        </General>
    </Domain>
</CycloneDDS>
```

环境变量 (写入 `~/.bashrc`):

```bash
export ROS_DOMAIN_ID=45
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_profile.xml
```

验证 (需与工控机同网段):

```bash
source /opt/ros/humble/setup.bash
ros2 topic list    # 应能看到工控机/上肢主控的话题
```

## 2. Python 视觉栈依赖

使用系统 python3 (与 ROS2 一致), 不用 conda。

```bash
pip3 install -r ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/requirements-orin.txt
```

依赖清单见 `requirements-orin.txt`, 要点:

| 包 | 说明 |
|----|------|
| pyorbbecsdk2==2.1.1 | 奥比中光相机 SDK (注意是 **pyorbbecsdk2**, 内置 OrbbecSDK v2.8.6 原生库)。旧包 `pyorbbecsdk` 已被它覆盖安装, 两者模块名相同, 不要装错 |
| onnxruntime | YOLO 推理。aarch64 用 PyPI CPU 版; 如需 GPU 加速, Jetson 需从 NVIDIA 渠道取 TensorRT/onnxruntime-gpu 轮子, 【待填实际方案】 |
| opencv-python | 含 aruco (二维码/标定用) |
| open3d | 仅 `test_grasp_single.py` 抓取点云测试用, aarch64 无官方轮子, 可选装 |

### 2.1 Orbbec USB udev 规则 (必须, pip 不会自动安装)

pyorbbecsdk2 内置 udev 规则和安装脚本, 需手动执行:

```bash
sudo $(python3 -c "import pyorbbecsdk, os; print(os.path.dirname(pyorbbecsdk.__file__))")/shared/install_udev_rules.sh
```

脚本将 `99-obsensor-libusb.rules` (Orbbec 全系 USB 设备 idVendor=2bc5 的
`MODE 0666` 权限) 拷到 `/etc/udev/rules.d/` 并 reload udev。
**不装则非 root 用户打不开相机** (USB 设备权限错误)。

验证 (相机插上后):

```bash
ls /etc/udev/rules.d/99-obsensor-libusb.rules   # 规则存在
lsusb | grep 2bc5                                # 能识别到相机
ls /dev | grep -iE "gemini|femto|astra"          # 设备节点已建 (型号相关, 无输出也不一定失败)
```

依赖验证:

```bash
python3 -c "from pyorbbecsdk import Pipeline; print('orbbec ok')"
python3 -c "import onnxruntime, cv2.aruco, yaml, numpy; print('vision deps ok')"
```

## 3. EtherCAT (SOEM + 夹爪)

```bash
cd ros2_ws/src
git clone https://github.com/OpenEtherCATsociety/SOEM.git
cd SOEM && git checkout v1.4.0
mkdir build && cd build
cmake -DCMAKE_INSTALL_PREFIX=../install ..
make -j$(nproc) && make install
ls ../install/lib/libsoem.a   # 验证
```

夹爪权限: 生产环境走 systemd `AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN`
(见 `scripts/README.md`, 安装自启后自动生效); 手动测试用 `sudo -E` 或
`scripts/setup_gripper_caps.sh` (注意每次 colcon build 后需重新执行)。

**USB 转网口插入后先做两件事** (前一台 Orin 实测踩坑):
1. 复查 UEFI 启动顺序, 防止网络启动卡 2-3 分钟 (见 9.1)
2. 把该网卡设为 NetworkManager unmanaged, 防止 DHCP 引发网络异常 (见 9.2)

## 4. 项目代码与构建

```bash
git clone <仓库地址> 【待填】
cd <项目>/ros2_ws
source /opt/ros/humble/setup.bash
colcon build            # 全量构建, furance_sim 必须包含 (node_manager 由它提供)
source install/setup.bash
```

### 4.1 控制系统后端 (Python)

依赖由 pyproject 声明 (fastapi/uvicorn/pydantic/websockets), 开发模式:

```bash
cd shared && pip3 install -e .
cd ../robot_control/backend && pip3 install -e ".[dev]"
```

### 4.2 控制系统前端 (npm)

需 Node.js >= 18 (开发机为 node 22)。依赖在 `robot_control/frontend/package.json`
(vue3 / element-plus / axios / vite), `npm install` 会拉全。

```bash
# Node.js 安装 (若无): https://github.com/nodesource/distributions#debian-ubuntu
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs

cd robot_control/frontend
npm install               # 生产构建 (自启服务需要 dist/): npm run build
```

注意: `scripts/install_autostart.sh` 会自动执行 `npm install && npm run build`,
装完自启服务即可跳过本步手动构建。

## 5. 数据恢复清单 (git 里没有, 必须手动恢复)

| 文件 | 位置 | 说明 |
|------|------|------|
| YOLO 模型 `best.onnx` | `orbbec_vision/models/train/weights/` | 权重目录未被 git 跟踪, 从工控机拷贝 |
| `weights/`, `yolo26n.pt` | `orbbec_vision/` | 同上, 未跟踪 |
| 相机外参 | `orbbec_vision/camera_config.yaml` (已跟踪) + 场景级 `T_base_qr` 存储文件 【待填路径】 | 二次标定产物, 丢了需重新标定 |
| 示教点 | `robot_control/backend/data/teach/` | 已跟踪, clone 即有; Orin 上如有增量需同步 |

恢复后验证:

```bash
python3 -c "
import yaml
cfg = yaml.safe_load(open('ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/yolo_config.yaml'))
print(cfg['model_path'])
"
# 确认 model_path 指向的文件存在, 且路径前缀与新机器一致 (绝对路径含 /home/kty, 换用户名需改)
```

## 6. 服务自启动

```bash
cd <项目>/scripts
./install_autostart.sh
```

安装 `furance-node-manager` / `furance-backend` / `furance-frontend` 三个 systemd
服务, DDS 环境变量由 wrapper (`scripts/furance-node-manager.sh`) 注入。

验证:

```bash
systemctl status furance-node-manager furance-backend
journalctl -u furance-node-manager -f
```

## 7. 整机验证

```bash
# 相机节点 + YOLO
# 【待填: camera_manager_node 启动命令 / 由 node_manager 拉起】

# 夹爪
ros2 service call /gripper_node/EC_grippers_control control_interfaces/srv/ECGrippersControl \
  "{gripper_name: 'right', command: 'open', width_mm: 0.0}"

# 夹爪节点 (手动, 不走 systemd)
sudo -E bash -c 'source /opt/ros/humble/setup.bash && source install/setup.bash && \
  ros2 launch grippers_control gripper.launch.py'
```

## 8. 装机后立即做备份

```bash
# 在工控机上配好 ssh 免密后, 在 Orin 上定时跑 (cron 每日):
rsync -av --delete \
  ~/furance_robot/ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/{models,weights,yolo_config.yaml,camera_config.yaml} \
  工控机用户@工控机IP:~/orin_backup/
```

标定数据、模型权重、示教点变更后手动同步一次。原则: **Orin 上不允许存在唯一副本的文件**。

## 9. 已知问题 (前一台 Orin 实测踩坑)

### 9.1 开机卡 2-3 分钟 -- UEFI 网络启动 (PXE) 优先于硬盘

**现象**: 不接无线网卡时开机卡 2-3 分钟才进系统; 在 UEFI 里调好启动顺序后,
一旦插入 EtherCAT 的 USB 转网口, 启动顺序又被重置, 卡顿复现。

**根因**: UEFI 启动项里网络启动 (PXE) 排在硬盘前面, PXE 探测超时约 2-3 分钟。
USB 网卡接入时 EDK2 重新枚举启动设备, 新建 PXE 启动项并排到前面, 顶掉手工调好的顺序。

**解决 (二选一, 均需复查)**:

方式 A -- 进 UEFI 菜单 (开机时按住 ESC 或用串口线):

```
Boot Maintenance Manager → Boot Options → Change Boot Order
  把内部存储 (NVMe/SD) 移到最前, 网络项 (UEFI PXEv4/PXEv6/HTTPv4...) 删除或移到最后
```

方式 B -- 系统内用 efibootmgr (JetPack 5.x 之后的 EDK2 UEFI 支持):

```bash
efibootmgr -v                    # 记录启动项编号和顺序
sudo efibootmgr -b 000X -B      # 删除网络启动项 (000X 为 PXE/HTTP 项编号)
sudo efibootmgr -o 0001,0002     # 显式指定顺序, 硬盘/OS 项在前
```

**重要**: 这不是一劳永逸的--**每次增删 USB 网卡 (含 EtherCAT 转接盒) 后都要
`efibootmgr -v` 复查一次启动顺序**。硬件拓扑固定后 (USB 转网口常插) 调一次即可。
装好 EtherCAT USB 网卡后先重启验证一次不卡, 再进入后续步骤。

### 9.2 EtherCAT 的 USB 转网口被 DHCP 分配地址, 系统初始化时网络通讯异常

**现象**: EtherCAT 用的 USB 转网口被 DHCP 分配了 IP, 开机初始化阶段网络通讯
经常出问题。

**根因**: SOEM (EtherCAT 主站) 走**原始以太网帧 raw socket, 完全不需要 IP**。
NetworkManager 对该网卡做 DHCP 反而有害: 开机等待 DHCP 超时拖慢初始化;
更糟的是 DHCP 给它分到与主网卡相同网段的地址时, 路由表冲突, 整机网络异常。

**解决**: 让 NetworkManager 完全不管理这块网卡 (按 MAC 精确匹配, 不影响其他网卡):

```bash
# 1. 插上 USB 转网口, 查 MAC (link/ether 字段)
ip link show | grep -A1 "enx"    # USB 网卡接口名一般为 enx<MAC>

# 2. 写入 unmanaged 配置 (AA:BB:CC:DD:EE:FF 换成实际 MAC)
sudo tee /etc/NetworkManager/conf.d/no-ethercat.conf <<EOF
[keyfile]
unmanaged-devices=mac:AA:BB:CC:DD:EE:FF
EOF

# 3. 重启 NetworkManager
sudo systemctl restart NetworkManager
nmcli device     # 该网卡 STATE 应为 "unmanaged"
```

验证:

```bash
ip addr show enx<MAC>    # 不应有任何 inet/inet6 地址 (SOEM 不需要)
ip route                 # 路由表不应出现该网卡, 无网段冲突
# 夹爪功能不受影响: grippers_control 用 raw socket, 与 IP 配置无关
```

**注意**:
- 必须按 MAC 匹配, 不要按 `interface-name:enx*` 一刀切--将来接其他 USB 网卡
  (如调试用) 也会被误伤
- 换了 USB 转网口硬件 = 换了 MAC, 需更新配置文件
- 若开机仍有 "A start job is running for Network Manager..." 等待, 可再执行
  `sudo systemctl mask NetworkManager-wait-online.service` (会让 systemd 不再
  等所有网卡就绪, 对本机无影响, 但依赖网络就绪的服务启动时机不再受保护)
