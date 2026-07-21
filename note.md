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

2026/6/12
机器人控制系统：
1.  机器人双臂协同角度控制、末端坐标控制开发（100%）
2. 控制系统添加相机管理功能，视线相机视频流推送
硬件集成：
1. nvidia orin控制板到货，控制系统移植部署过程中发现usb口协议不对，断电后掉系统等问题，已返厂维修，预计下周到货
协调跟踪事项：
1. 底盘外壳+防尘设计供应商已收到任务，需要跟踪进度，本周进度无反馈
2. 手臂碰撞检测供应商预计3周开发完毕，这周为第一周
3. 充电桩接触头暂未发货

2026/6/17
机器人控制系统：
1.  相机完成右机械臂手眼标定全流程，并封装为独立脚本，供后续头部和左手使用
2. 二维码定位识别功能基本开发完毕，当前存在识别跳变，暗光处识别不清晰等问题，计划采取红外画面+红外打光，效果待验证
3. 相机功能并入控制系统（50%）
4. 夹爪模块功能验证（50%）
硬件集成：
1. nvidia orin控制板厂家确认是usb2.0口，正在协调能否更换为3.0，同时新提交采购
2. 夹爪到货，由于前期沟通存在误解导致型号错误，已沟通厂家更换夹爪，预计4周。当前在现有夹爪设备上进行通讯验证和模块开发，验证完毕后寄回错误型号夹爪，不影响开发进度。
3. 上周底盘保险丝烧毁原因已经找到，机器人上身控制板短路烧坏，已协调厂家寄送新的控制板
协调跟踪事项：
1. 底盘外壳+防尘设计已有工程师沟通跟进
2. 手臂碰撞检测供应商预计3周开发完毕，这周为第二周
3. 充电桩接触头暂未发货

2026/6/26
机器人控制系统：
1. 相机功能并入控制系统,工作流视觉功能开发完成，实现视觉功能模块获取位姿传递到下一个movep运动（100%）
2. 实现工作流编排中点位的偏移功能，支持世界坐标和工具坐标下的点位偏移
3. 控制系统中添加底盘的定距离定角度控制，并且并入工作流编排
硬件集成：
1. nvidia orin控制板厂家确认无法更换为3.0通讯接口板，已经协调采购退款，并且计划提交新的orin采购
2. 因供应商缺货，本周机器人上身控制板无修复进度，已经将旧的寄回去给厂家测试调试
3. 底盘外壳到货，但因缺少上身控制版无法升高机器人，测试装配外壳
协调跟踪事项：
1. 手臂碰撞检测供应商预计3周开发完毕，这周为第三周，多次询问开发进度没有得到回复
2. 充电桩接触头未发货
WAIC进度跟踪：
1. 由于缺少orin做主控和电动夹爪，已经将转炉R2机器人搬运出厂，拿其中的主控板和电夹爪替代
2. 控制系统部署orin（50%）
3. 展示用抓取动作编排，空手模拟运动已经实现，后续虚适配夹爪和道具后统一联调（30%）
4. 夹指法兰设计（30%）
5. 现场展示用道具设计（10%）



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

1. 相机USB开机没有自动识别
2. 一键清楚除node manager以外的残留节点


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

### Today TODO
1. 二维码识别功放入test_ir中测试，优化后集成进视觉模块
2. 检查添加了视觉后的工作流
3. 视觉相机添加开关，没任务时不进行推流
4. 运动到了机械臂实际限位，moveit没有报错

### P0
1. 夹爪接线
2. 夹爪模块开发，并入工作流
3. orin开机自启动脚本