# 调试记录
## 项目跟踪
2026/5/22
1. 在底盘导航功能测试中，发现机器人升降机在底部时双臂会影响激光雷达定位导航。当前以升高升降机作为解决方案，但是在底盘移动与停止时会加剧机器人抖动，后续等夹爪到货安装后抓取取样杆进行测试。
2. 底盘导航API测试完成，可进行运控系统的开发。
3. 上肢接口测试中，出现ROS2多机通讯问题，正在解决
需要协调事项：
1. 左臂7轴电机EC_out异常
2. 底盘外壳设计进度供应商本周无反馈，需要跟踪

2026/5/29
开发接口均已测试完毕，机器人控制系统已经完成：
1. 导航地图获取、导航点/路径下发并执行、底盘状态监控
2. 手臂状态监控、双臂角度控制、末端坐标控制及示教和点位存储功能
3. 机器人子任务工作流编排与存储
需要协调事项：
1. 机器人底盘外壳设计供应商本周无进度反馈
2. 左臂EC_out异常
3. 升降机及上身需要做防尘结构设计
4. 机械臂需要添加物理急停功能
5. 机械臂需要添加碰撞检测功能
6. 供应商未提供充电桩接触头，无法测试自动充电接口

1. 底盘需要设计外壳
2. 升降机及上身需要防尘
3. 机械臂需要碰撞检测
4. 充电桩接触头需要提供

2026/6/5
机器人控制系统：
1. 机器人工作流执行测试，手臂多点位移动已经通过（导航待测试，视觉、夹爪待开发）
2. 机器人双臂协同角度控制、末端坐标控制开发（50%）
3. ROS2节点管理功能（100%）
4. 日志查询功能（100%）
硬件集成：
1. 上肢物理急停已安装
2. 交换机+无线AP已经安装，网路全部打通
3. nvidia orin控制板到货，控制系统移植部署进度（10%）
协调跟踪事项：
1. 底盘外壳+防尘设计供应商已收到任务，需要跟踪进度
2. 手臂碰撞检测供应商预计3周开发完毕
3. 充电桩接触头暂未发货

## 控制系统
### 启动指令
```bash
ROS2_MODE=real python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
### DDS配置
```bash
export ROS_DOMAIN_ID=45
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_profile.xml
```

## 上肢主控
### 常用配置
ip 192.168.1.100
user: jhc
password: qm1618

### 升降机构控制
```bash
# 头部偏转角
ros2 service call /ascend_control interface_pkg/srv/AscendControl "{ascend_pos: 100.0, ascend_speed: 20, reserve: 0}"

#头部俯仰控制，没有限位。输入控制在0-35
ros2 service call /head_control interface_pkg/srv/HeadControl "{head_angle: 30.0, head_speed: 10, reserve: 0}" 

# 腰部高度控制0-600
ros2 service call /waist_control interface_pkg/srv/WaistControl "{waist_angle: 450.0, waist_speed: 20, reserve: 0}"

# 电机控制
ros2 service call /motor_control interface_pkg/srv/MotControl "{angle: 90.0, speed_waist: 10, reserve_1: 0, pos: 0.0, speed_ascend: 0, reserve_2: 0, head_angle: 0.0, speed_head: 0, reserve_3: 0}"
# angle：高度控制

ros2 service call /motor_control interface_pkg/srv/MotControl "{angle: 90.0, speed_waist: 10, reserve_1: 0, pos: 30.0, speed_ascend: 0, reserve_2: 0, head_angle: 0.0, speed_head: 0, reserve_3: 0}"
# pos：头部偏转角

ros2 service call /motor_control interface_pkg/srv/MotControl "{angle: 90.0, speed_waist: 10, reserve_1: 0, pos: 0.0, speed_ascend: 0, reserve_2: 0, head_angle: 30.0, speed_head: 10, reserve_3: 0}"
# head_angle： 头部俯仰控制

ros2 service call /robot_enable_control interface_pkg/srv/RobotEnableControl "{enable: ture}"
ros2 service call /robot_clear_error interface_pkg/srv/ClearError "{clear_error: true}"
ros2 service call /move_joint_positions interface_pkg/srv/MoveToJointPositions "{left_joints: [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0], right_joints: [10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]}"
ros2 service call /move_joint_positions interface_pkg/srv/MoveToJointPositions "{left_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], right_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}"

ros2 service call /global_speed_set interface_pkg/srv/GlobalSpeedSet "{speed: 20.0}"
```
```bash
ros2 launch t1_moveit_config t1_moveit_headless.launch.py use_sim:=false rviz:=true
ros2 launch t1_moveit_config t1_moveit_headless.launch.py use_sim:=false rviz:=false

```
目前正在测试完整的建图导航流程，流程中出现的问题：
1. 升降机在底部时手臂会被识别为障碍物导致无法导航（通过升高升降机临时解决，但升高后重心太高容易晃动）
2. 升降机的控制接口文档描述错误（已经解决）
3. 升高后建图导航无法通过1.5m的通道（正在排查）
导航功能还需要测试在考虑上肢碰体积和抓握取样棒的情况下移动的情况，厂家并未公开这些参数，无法自己测试只能远程沟通，效率比较低。
以及自动充电的功能（当前没有在底盘看到充电的电极，供应商目前没有回话
底盘接口测试完毕后上肢运动还需要过一边，看下是否有和升降电机一样的文档错误，全部测试完毕后才能进行后续的开发

## 调度系统
``` bash
cd /home/kty/Desktop/furance_robot/dispatch/backend
python3 -m uvicorn app.mock.robot_mock:mock_app --host 0.0.0.0 --port 9001
python3 -m uvicorn app.mock.sampler_mock:mock_app --host 0.0.0.0 --port 9002
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## 无线AP
```
192.168.1.254
turin
turin
```

### TODO
1. 相机驱动调试
2. 自动充电
3. 夹爪装配与控制
4. 双臂moveJ规划

### Orin到货TODO
1. 环境安装（ros2,cycloneDDS,奥比中光SDK,EtherCat驱动，其他依赖）
2. ToDesk安装
3. 无线路由器配置
4. 相机多路视频流状态打通
5. 控制系统+相机状态打通
6. 夹爪功能实现


### 问题记录
1. urdf中上身高度描述与实际不符（已修复）
2. 右臂的指令与反馈是相反的（发送到10度位置，反馈为-10度位置）（已修复）
3. 上肢无急停
4. 无碰撞检测
5. 升降机构无防尘，需要明确后续维修计划
6. 错误清除可能要多次


## 视觉模块（旧代码分析）

旧视觉代码位于 `ros2_robot/src/python_pkgs/python_pkgs/vision/`，基于 ASCamera 驱动（hp60c 型号），使用非标压缩图像话题。以下是各文件功能描述：

### camera_handler.py — 单相机帧管理器
- 管理单个相机的 RGB（CompressedImage）+ Depth（Image）话题订阅
- 保存最近一帧 RGB 和深度图，供检测调用
- 后台检测线程：检测到有订阅者时触发 YOLO 推理，发布标注图像到 `/yolo_detections/{name}` 和 JSON 检测结果到 `/yolo_detections/{name}/result`
- 问题：缺少 `String` 和 `json` 的 import

### yolo_dete.py — YOLOv8 ROS2 节点
- `YoloDetector`：封装 YOLO 检测/分割模型（ONNX），支持 detect/segment 模式
- `YoloRos2Node`：ROS2 节点，参数化相机内参（fx/fy/cx/cy），支持三相机（当前仅启用 1 个），提供 `/yolo_inference` 服务
  - 服务输入：camera_id、target_class、mode
  - 服务输出：目标 3D 坐标（camera 坐标系，从深度图中值计算）、标注图像
- `YoloClient`：服务客户端 + 话题订阅客户端，支持单帧调用和持续订阅两种模式
- 相机话题：`/camera/camera/color/image_raw/compressed`（ASCamera 非标压缩话题）

### QR_dete.py — ArUco 二维码检测服务
- `ArucoDetectorNode`：提供 `/QR_detection` 服务
  - 输入：ROS Image + qr_id + qr_size
  - 输出：二维码在 torso 坐标系下的 3D 位置 + 投影角度
- 使用 DICT_4X4_100 字典，硬编码 camera→torso 变换矩阵（R_camera_to_torso, t_translation）
- 相机内参硬编码（fx=614, fy=614, cx=320, cy=240）
- 问题：硬编码了旧工程的 venv 路径 `/home/wheel_arm_ws/src/python_pkgs/venvs/yolo`

### QR_publisher.py — 连续 ArUco 检测与位姿发布
- `QR_Publisher_Node`：订阅 `/camera/color/image_raw` 持续检测 ArUco 标记
- 发布标注图像到 `/image_qr`，合并位姿 JSON 到 `/qr_pose`（ids/points/angles）
- 支持多种标记尺寸（0.15m, 0.058m, 0.058m），通过标记 ID 索引
- `QR_Subscriber_Node`：订阅 `/qr_pose` 的客户端节点
- 问题：硬编码了 Docker 内路径 `/workspaces/isaac_ros-dev/src/python_pkgs/venvs/yolo`

### pose_trans.py — 静态变换链与运动客户端
- `PoseTransformer` 节点：订阅 `/aruco_single/pose`，计算物体在 base_link 和 waist_Link 下的位姿
- 静态变换链：camera→base（固定 TF）→ QR tag（检测）→ object（固定偏移）
- 工具函数：PoseStamped 线性插值 + Slerp 姿态插值、沿末端 X/Z 轴平移
- 运动客户端类：MovePClient、MoveLClient、MoveJointPositionsClient、MoveWaistClient
- 主流程：等待二维码 → 计算 waist 系下抓取位姿 → MoveP → MoveL 抓取 → 回收

### pose_trans_tf.py — TF2 动态位姿变换
- `PoseTransformTool`：使用 tf2_ros 动态查询坐标系变换
- `get_averaged_tf`：多次采样 + 异常值剔除（2σ）+ 四元数对齐的均值滤波
- 变换链：camera_marker→base_link→waist_Link
- `LiftClient`：升降机控制客户端
- 主流程：标定物体在 marker 下位姿 → 计算 waist 系下抓取位姿 → 含容错检查的抓取流程

### cal_tag_to_hand.py — 手眼标定工具
- `CalibrationTool`：计算末端执行器到 Marker 的固定变换
- 流程：示教移动末端接触 Marker → 记录末端在 base 下位姿 → 记录 Marker 在 base 下位姿 → 计算 T_eed_marker
- 使用 tf2_ros + 均值滤波

### add_obstacle.py — 导航障碍物自动添加
- 基于二维码检测结果，在检测到的标记周围自动添加 3D 碰撞障碍物（BOX/CYLINDER）
- 使用 `ManageObstacle` 服务管理障碍物生命周期
- 坐标变换：局部坐标系 → 全局坐标系（绕 Z 轴旋转 + 平移）

### 辅助工具
- `reverse.py`：计算 4x4 齐次变换矩阵的逆变换
- `pt2onnx.py`：Ultralytics YOLO 模型导出为 ONNX 格式
- `best2.onnx`：YOLO 检测模型权重（10MB）

### 关键问题汇总
| 问题 | 影响 |
|------|------|
| 使用 ASCamera 非标压缩话题 | 无法直接适配 Orbbec 相机 |
| 相机内参硬编码 (614, 614, 320, 240) | 不同相机/分辨率需重新标定 |
| camera→torso 变换矩阵硬编码 | 相机安装位置变化需重新标定 |
| venv 路径硬编码 | 部署到新机器需修改 |
| camera_handler.py 缺少 import | 无法正常运行 |
| 仅启用 1 个相机 | 三相机方案未激活 |

## 视觉模块（新 — Orbbec 相机集成）

### 架构
- 3 个 Orbbec 相机节点，通过 namespace 隔离：`/camera_1`、`/camera_2`、`/camera_3`
- 每个相机发布标准话题：`/color/image_raw`、`/depth/image_raw`
- `vision_detect_node` 提供 `/vision_detect` ROS2 服务，对接控制系统 HTTP API
- 三相机 RViz 可视化通过 launch 文件一键启动

### 环境准备

首次部署需安装奥比中光 udev 规则（否则普通用户无 USB 权限打开相机）：

```bash
sudo cp /opt/ros/humble/share/orbbec_camera/udev/99-obsensor-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 内核 UVC 驱动冲突

如果内核 `uvcvideo` 驱动先占用了相机（创建 `/dev/video*`），Orbbec SDK 的 libusb 后端无法打开设备，日志报 `usbEnumerator openUsbDevice failed!`。

**解决方法：** 解绑 uvcvideo 驱动

```bash
# 查看相机在哪个 USB 端口（如 3-2）
lsusb | grep Orbbec

# 解绑 uvcvideo 驱动
for iface in /sys/bus/usb/drivers/uvcvideo/3-2:1.*; do
  sudo sh -c "echo -n '$(basename $iface)' > /sys/bus/usb/drivers/uvcvideo/unbind"
done
```

如需永久解决，可在 udev 规则中添加 `RUN+="/bin/sh -c 'echo $kernel > /sys/bus/usb/drivers/uvcvideo/unbind'"`，或将 `uvcvideo` 加入黑名单（会影响其他 UVC 摄像头）。

### 调试命令

```bash
# 构建
cd /home/kty/Desktop/furance_robot/ros2_ws
colcon build --packages-select control_interfaces python_pkgs
source install/setup.bash

# 查看 VisionDetect 服务定义
ros2 interface show control_interfaces/srv/VisionDetect

# 查看三相机话题
ros2 topic list | grep camera

# 查看单个相机图像
ros2 run rqt_image_view rqt_image_view /camera_1/color/image_raw

# 查看深度图
ros2 run rqt_image_view rqt_image_view /camera_1/depth/image_raw

# 调用视觉检测服务
ros2 service call /vision_detect control_interfaces/srv/VisionDetect "{camera_id: 'camera_1', scene: 'grasp_top'}"

# 查看 TF 树
ros2 run rqt_tf_tree rqt_tf_tree

# 启动视觉相机 + vision_detect 节点（默认只启动 camera_1，避免三相机同时冲爆带宽）
ros2 launch python_pkgs three_cameras.launch.py enable_rviz:=false

# 只启动 camera_2
ros2 launch python_pkgs three_cameras.launch.py enable_camera_1:=false enable_camera_2:=true enable_camera_3:=false enable_rviz:=false

# 只启动 camera_3
ros2 launch python_pkgs three_cameras.launch.py enable_camera_1:=false enable_camera_2:=false enable_camera_3:=true enable_rviz:=false

# 启动当前选中相机 + vision_detect + RViz 可视化
ros2 launch python_pkgs three_cameras.launch.py enable_rviz:=true

# 单独启动 vision_detect 节点
ros2 run python_pkgs vision_detect

# 控制系统通过 node_manager 启动视觉（前端相机页面会自动调用）
# POST /api/v1/robot/robot_001/camera/publish/start {"camera_id":"camera_1"}
# POST /api/v1/robot/robot_001/camera/publish/stop
```
