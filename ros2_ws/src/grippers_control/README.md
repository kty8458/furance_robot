# EtherCAT 夹爪 (SOEM) 环境配置与使用

JODELL EPG-L80-400 EtherCAT 夹爪控制包。基于 SOEM 走 EtherCAT 实时通信。

## 1. SOEM 安装 (前置, 必须先做)

SOEM (Simple Open EtherCAT Master) 未随系统安装, 需手动编译。

```bash
# 进入 ros2_ws/src (与 grippers_control 同级)
cd /home/kty/Desktop/furance_robot/ros2_ws/src

# 克隆 SOEM
git clone https://github.com/OpenEtherCATsociety/SOEM.git
cd SOEM
git checkout v1.4.0   # 建议用稳定版本

# 编译安装 (安装到 SOEM/install)
mkdir build && cd build
cmake -DCMAKE_INSTALL_PREFIX=../install ..
make -j$(nproc)
make install

# 验证
ls ../install/lib/libsoem.a        # 应存在
ls ../install/include/soem/ethercat.h  # 应存在
```

安装后 `SOEM/install/lib/libsoem.a` 就是 CMakeLists.txt 默认链接的库。

### SOEM 安装到别处的情况
如果 SOEM 装在其他路径, 编译 grippers_control 时用环境变量覆盖:
```bash
export SOEM_ROOT=/your/soem/install/path
colcon build --packages-select grippers_control
```

## 2. 网卡配置

EtherCAT 需要独占一个有线网卡 (原始 socket)。夹爪通过 USB-Ethernet 转接连接。

```bash
# 查看网卡
ip link show
# 找到 enx 开头的 USB 网卡, 例如 enx00e01b76020c

# 确认网卡未配置 IP (EtherCAT 独占, 不要有 IP)
sudo ip addr flush dev enx00e01b76020c
sudo ip link set enx00e01b76020c up
```

修改 `config/gripper.yaml` 的 `interface_name` 为你的网卡名:
```yaml
gripper_node:
  ros__parameters:
    interface_name: "enx00e01b76020c"   # 改成你的网卡
```

## 3. 权限配置 (EtherCAT 需原始 socket)

EtherCAT 原始 socket 默认需要 root。两种方式:

### 方式 A: sudo 运行 (简单)
```bash
sudo -E env "PATH=$PATH" "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" \
  ros2 launch grippers_control gripper.launch.py
```

### 方式 B: udev 规则免 sudo (推荐长期)
给特定网卡 CAP_NET_RAW 能力, 或用 setcap:
```bash
# 给可执行文件设置网络能力 (需每次重新 build 后重设)
sudo setcap cap_net_raw,cap_net_admin=eip \
  install/grippers_control/lib/grippers_control/gripper_node
```

## 4. 编译

```bash
cd /home/kty/Desktop/furance_robot/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select control_interfaces grippers_control
source install/setup.bash
```

注意: 必须先 build control_interfaces (接口), 再 build grippers_control (依赖接口)。

## 5. 连接测试 (CLI, 不启动 ROS2)

`gripper_control` 是独立 C 程序, 读取 config/gripper.yaml, 直接控夹爪, 用于硬件快速验证。

```bash
cd /home/kty/Desktop/furance_robot/ros2_ws

# 状态 (先测这个, 确认通信)
sudo ./install/grippers_control/lib/grippers_control/gripper_control right status

# 张开
sudo ./install/grippers_control/lib/grippers_control/gripper_control right open

# 闭合
sudo ./install/grippers_control/lib/grippers_control/gripper_control right close

# 移动到指定宽度 (mm)
sudo ./install/grippers_control/lib/grippers_control/gripper_control right move 40

# 左夹爪
sudo ./install/grippers_control/lib/grippers_control/gripper_control left open

# 指定配置文件
sudo ./install/grippers_control/lib/grippers_control/gripper_control \
  --config src/grippers_control/config/gripper.yaml right status

# 旧版用法 (网卡名覆盖 config)
sudo ./install/grippers_control/lib/grippers_control/gripper_control \
  enx00e01b76020c right move 40
```

### SDO 读取 (诊断)
`read_gripper_sdo` 读取夹爪 SDO 参数 (诊断用):
```bash
sudo ./install/grippers_control/lib/grippers_control/read_gripper_sdo \
  enx00e01b76020c 2   # 网卡名 从站索引
```

## 6. ROS2 节点运行

```bash
# 启动节点 (需 sudo, EtherCAT 原始 socket)
sudo -E env "PATH=$PATH" "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" \
  ros2 launch grippers_control gripper.launch.py

# 或指定配置
sudo -E env "PATH=$PATH" "LD_LIBRARY_PATH=$LD_LIBRARY_PATH" \
  ros2 launch grippers_control gripper.launch.py config:=/path/to/gripper.yaml
```

## 7. ROS2 service 控制

节点提供 `/gripper_node/control` service (control_interfaces/srv/ECGrippersControl):

```bash
# 张开右夹爪
ros2 service call /gripper_node/control control_interfaces/srv/ECGrippersControl \
  "{gripper_name: right, command: open, width_mm: 0.0}"

# 闭合左夹爪
ros2 service call /gripper_node/control control_interfaces/srv/ECGrippersControl \
  "{gripper_name: left, command: close, width_mm: 0.0}"

# 右夹爪移动到 40mm
ros2 service call /gripper_node/control control_interfaces/srv/ECGrippersControl \
  "{gripper_name: right, command: move, width_mm: 40.0}"

# 读取状态
ros2 service call /gripper_node/control control_interfaces/srv/ECGrippersControl \
  "{gripper_name: right, command: status, width_mm: 0.0}"
```

## 8. 状态监控

节点持续发布 `/gripper_node/status` (control_interfaces/msg/ECGrippersStatus):
```bash
ros2 topic echo /gripper_node/status
```
字段: 夹爪名, 从站索引, online, working_counter, claw_status, 错误码, 当前宽度, 目标位置, 母线电压, 驱动温度。

## 排错

- **SOEM static library not found**: SOEM 未装或路径不对, 见第1步。用 `SOEM_ROOT` 环境变量指定。
- **No EtherCAT slaves found**: 网卡名错 / 网卡没 up / 线没连 / 夹爪没上电。
- **EtherCAT initialization failed**: 需 sudo 或 setcap, 见第3步。
- **Invalid slave index**: config/gripper.yaml 的 slave_index 和实际 EtherCAT 拓扑不符, 用 read_gripper_sdo 确认从站索引。
