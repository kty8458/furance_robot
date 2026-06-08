我现在想设计一个轮式双臂的机器人控制系统和一个部署在现场的调度系统，需求如下：
1. 机器人的工控机上部署一套控制系统以及页面，系统为Ubuntu22.04需求如下：
    - 采取B/S架构实现
    - 控制系统后台使用fastapi实现
    - 后台与页面的通讯使用http
    - 后台与调度系统的控制通讯使用http
    - 后台与调度系统的状态上报使用websocket
    - 控制系统与机器人的执行代码分开，执行代码为ROS2通讯，此处不考虑实现，仅考虑接口功能，通讯使用ROS2的service
    - 完整的日志存储，包含所有ROS2node的日志
    - 开机自启动，进程保护程序
    - 异常上报
    - 打包后一键部署
    - 对ROS2节点的管理，包括状态监控，开启与停止

    功能包含
    - 机器人上肢归零位下发
    - 机器人上肢抓取与放置任务下发
    - 机器人移动指令下发
    - 机器人夹爪开闭指令下发
    - 机器人高度上升下降指令下发
    - 机器人充电指令下发
    - 机器人使能+清错指令下发

    预备功能：
    - 夹爪ROS2模块的开发，夹爪通讯基于EtherCat
2. 现场控制柜上部署调度系统以及页面，系统为win10,需求如下：
    - 采取B/S架构实现
    - 数据库使用本地数据库sqlLite
    - 开机自启动，包含进程保护程序
    - 与机器人工控机使用http下发控制命令
    - 与机器人工控机基于websokct通讯获取状态
    - 与现场制样机设备通过websockt通讯进行电文通讯
    - 打包后一键部署

    功能包含：
    - 机器人上肢归零位下发
    - 机器人上肢抓取与放置任务下发
    - 机器人移动指令下发
    - 机器人夹爪开闭指令下发
    - 机器人高度上升下降指令下发
    - 机器人充电指令下发
    - 机器人使能+清错指令下发
    - 机器人的任务编排与存储
    - 机器人的状态信息接收与展示
    - 制样机任务的工作与停止指令下发
    - 制样机的状态信息接收与展示
    预备功能：
    - 与L2系统的通讯对接，触发编排好的任务执行

你需要使用supperpower的skill,与我讨论并完善需求文档，然后执行下面的任务：
1. 需求文档生成
2. 接口为文档生成，包含websoccker电文，http接口，ROS2接口
3. 基于Harness Engineering生成约束，包括：
    - CLAUDE.md
    - linter
    - setting.json
    - hook
    - CI
4. 开发计划，即等确认无误后能够直接基于计划进行开发

补充说明1：
1. 导航功能拓展：
    - 获取地图列表
    - 获取当前地图下的导航点位列表
    - 机器人移动所需参数为地图+导航点+速度
2. 机器人上肢移动拓展:
    - 抓取与放置的输入参数仅为目标（字符串）
    - 机器人控制系统上添加手臂运控接口，直接控制手臂末端（arm：{left,right}, angle:{joint1-7},position:{xyzrpy},coordniate:{baselink},method:{movep/moveL/moveJ})
    - 机器人控制系统上添加当前机械臂角度存储功能
    - 机器人手臂运控仅能在控制系统上完成

补充说明2：
1. 夹爪功能：
    - 夹爪接口添加left/right参数
    - 添加指定力矩的参数

补充说明3：
1. 机器人控制系统前端页面添加运行日志的实时显示，包括后端系统日志与ROS2节点日志

补充说明4：
1. 调度系统需要增加预留功能，循环监听L2的指令执行任务

当前问题：
1. 在调度系统中，接口返回的信息均正常，但是页面没法正常显示，点击下拉框后没有数据
2. 机器基础指令和充电控制的按钮风格并未与其他的按钮统一

当前问题：
1. 一个任务模板应该是由多个人物组成
2. 在任务模板这里需要能够看到模板下面的全部任务
3. 执行历史显示的是人物

现在我们来完善机器人控制系统的相关功能并进行调试：
1. 在根目录下面创建一个ros2的工作空间
2. 完成ros2接口包实现与编译
3. 创建ros2的node,用于模拟导航移动，手臂运控，夹爪闭合，状态上报（随机变化数值）
4. 要求有完整的日志记录，用于测试前端日志显示
5. 实现通过控制系统对这些ros2节点的启停与监控

修复bug：
1. 在node未开启时，下发控制命令前端返回200没报错，后台的日志：
INFO:     127.0.0.1:45100 - "POST /api/v1/robot/robot_001/home HTTP/1.1" 200 OK
Failed to execute async callback
Traceback (most recent call last):
  File "/home/kty/Desktop/furance_robot/robot_control/backend/app/ros2/runtime.py", line 71, in call_async_in_loop
    return future.result(timeout=5.0)
  File "/usr/lib/python3.10/concurrent/futures/_base.py", line 460, in result
    raise TimeoutError()
concurrent.futures._base.TimeoutError
Service /HomeCommand not available after 5s

2. node_manager不应该能控制自己的起停
3. 运行日志没有显示。需要每一个ros2node一片区域显示

1. 在状态发布节点起来之前状态监控显示为机器在线
2. 手臂状态显示异常
3. 运行日志只能显示进入页面后刷新的内容，并且切换到其他页面后日志消失
4. 手臂运动与视教存储接口异常：INFO:     127.0.0.1:47122 - "POST /api/v1/robot/robot_001/arm/teach/save HTTP/1.1" 500 Internal Server Error
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File "/usr/lib/python3.10/pathlib.py", line 1175, in mkdir
    self._accessor.mkdir(self, mode)
FileNotFoundError: [Errno 2] No such file or directory: '/opt/furance_robot/data/teach/robot_001'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/usr/lib/python3.10/pathlib.py", line 1175, in mkdir
    self._accessor.mkdir(self, mode)
FileNotFoundError: [Errno 2] No such file or directory: '/opt/furance_robot/data/teach'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/usr/lib/python3.10/pathlib.py", line 1175, in mkdir
    self._accessor.mkdir(self, mode)
FileNotFoundError: [Errno 2] No such file or directory: '/opt/furance_robot/data'

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "/home/kty/.local/lib/python3.10/site-packages/uvicorn/protocols/http/httptools_impl.py", line 409, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
  File "/home/kty/.local/lib/python3.10/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
    return await self.app(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/fastapi/applications.py", line 1054, in __call__
    await super().__call__(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/applications.py", line 112, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/middleware/errors.py", line 187, in __call__
    raise exc
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/middleware/errors.py", line 165, in __call__
    await self.app(scope, receive, _send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/routing.py", line 714, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/routing.py", line 734, in app
    await route.handle(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/routing.py", line 288, in handle
    await self.app(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/routing.py", line 76, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/kty/.local/lib/python3.10/site-packages/starlette/routing.py", line 73, in app
    response = await f(request)
  File "/home/kty/.local/lib/python3.10/site-packages/fastapi/routing.py", line 302, in app
    raw_response = await run_endpoint_function(
  File "/home/kty/.local/lib/python3.10/site-packages/fastapi/routing.py", line 213, in run_endpoint_function
    return await dependant.call(**values)
  File "/home/kty/Desktop/furance_robot/robot_control/backend/app/api/arm.py", line 27, in teach_save
    _get_arm_service(request).save_teach(robot_id, TeachPreset(
  File "/home/kty/Desktop/furance_robot/robot_control/backend/app/services/arm_service.py", line 24, in save_teach
    robot_dir.mkdir(parents=True, exist_ok=True)
  File "/usr/lib/python3.10/pathlib.py", line 1179, in mkdir
    self.parent.mkdir(parents=True, exist_ok=True)
  File "/usr/lib/python3.10/pathlib.py", line 1179, in mkdir
    self.parent.mkdir(parents=True, exist_ok=True)
  File "/usr/lib/python3.10/pathlib.py", line 1179, in mkdir
    self.parent.mkdir(parents=True, exist_ok=True)
  File "/usr/lib/python3.10/pathlib.py", line 1175, in mkdir
    self._accessor.mkdir(self, mode)
PermissionError: [Errno 13] Permission denied: '/opt/furance_robot'
INFO:     127.0.0.1:42934 - "GET /api/v1/robot/robot_001/arm/teach/list HTTP/1.1" 200 OK
INFO:     127.0.0.1:59406 - "POST /api/v1/robot/robot_001/arm/move HTTP/1.1" 422 Unprocessable Entity

示教管理bug修复，保存角度全为0，应该保存的数值为从状态监控中获取到的关节角度

1. 状态发布新增当前手臂的末端坐标与使用的坐标系
2. 手臂运控执行关节执行器应为7角度，添加参数末端坐标输入。如果为moveJ则角度必填，如果为moveP则坐标必填
3. 示教存储包含轴角度，末端坐标，和参考坐标系。执行时可选择使用哪种运动方式。添加点位更新功能


示教管理节点要显示存储的角度与坐标

对机器人控制系统做出以下优化：
1. 重构手臂运动控制模块：
    - 页面上的运动控制不再是手动输入关节角度后执行，而是更改为7个/6个“+”与“-”按钮，点击后直接发送机器人的控制指令，对发送频率做出控制。
    - 添加步长step设置，支持手动输入与滑调拖动
    - 在这个页面添加上下使能的按钮，以及使能状态的监控
    - 重构手部运控页面的布局，考虑到页面要在平板上使用，控制按钮要放在频率右以方便使用
2. 新增点位获取的ROS2service接口，以方便运控程序获取示教完成的点位数据

手臂运控的moveJ，moveP依然要保留。选择moveJ时为7个joint的+与-，选择moveP时为6个xyzrpy的+与-，并且保留坐标系选择

192.168.1.16主控
192.168.1.10底盘

视频还没有话题通讯
示教

ros2_ws下面添加了一些新的包，其中：
- t1_description
    - 机器人t1的urdf描述文件
- t1_moveit_config
    - t1上肢运动学的ros2moveit配置项目
- python_pkg
    - 一些状态发布等辅助文件
    - 模拟的手臂控制器
- control_interfaces
    - 接口
阅读并理解代码，实现以下功能：
- python_pkgs中的sim_arm_controller没有配置依赖，补齐
- 创建新的t1_moveit_launch.py并接入控制系统的后台ros2 node管理，这个launch文件不要出现图形化页面（不然会报错）
- 创建一个新的rviz launch的文件，用于在控制系统启动moveit launch文件后可视化机器人的关节角度
- 修改控制系统中有关机器人的状态监控数据显示，数据来源换成t1相关节点所发布的数据
- 完善控制系统中的movep和moveL接口，与moveit相关功能进行对接

重构导航模块，要求如下：
1. 控制系统的导航接口不再使用ros2,而是直接使用http向机器人的底盘发送指令
2. 机器人底盘控制接口json文档为docs/Magic商业导航接口-v1.4.4.json，符合apipost项目导入的格式
3. 底盘的baseurl为http://192.168.1.102:8888/yhs-robot/
4. 控制系统中的网页需要调用的接口有：
    1. /auth/token，用户名密码均为hardcode,在导航控制页面新增一个刷新按钮，点击后调用这个接口获取到token后本地保存供后续接口使用
    2. /data/list_maps 获取地图列表
    3. /data/poslist?map_name=7-1&type= 获取地图上的导航点
    4. /data/graph_list?map_name=inab 获取手绘路径列表
    5. /data/record_list?map_name=map 获取录制路径列表
    6. /task_queue/start 任务执行
    7. /task_queue/stop 任务停止
    8. /task_queue/task/is_finished 确认任务是否完成
    9. /task_queue/log?start_time=2024-08-30 8:30:37&end_time=2024-08-30 16:35:00&map_name=workshop 任务日志获取
    10. /cmd/recharge 自主回充
5. 其中导航点与路径列表显示在一起，统一作为任务执行的参数进行管理


修改 ros2 python_pkg的t1_joint_states_publisher节点，将/motor_feedback中的pos参数输入进joint_state中的SJ_Joint发布


根据sim_arm_controller的控制器，创建新的节点代码实现替换接口实现对实际机器人的控制：
1. 修改execute_trajectory函数，向/move_joint_positions服务发送interface_pkg/srv/MoveToJointPositions数据
2. 发送频率为10hz
3. 订阅joint_states话题，每次执行前要更新角度，避免在执行一只手臂的运动的时候另一只也运动
4. 将实际控制器节点添加进t1_moveit_headless.launch.py，替换sim controlle

t1_moveit_headless.launch.py需要两种模式，调试模式的时候要显示moveit的rviz控制台，部署模式取消控制台，可由无显示器的服务器通过node manager启动在后台运行

当前的问题：
1. 通过调整urdf的轴方向，当前已经做到了实际位置与rviz位置中保持一致，但是运行出现了右手的数值均为反向的问题（即实机角度全为+10度，moveie规划组显示数值为-10度）导致运控规划反向。如何解决

在ros2_ws的python_pkg创建代码，为rtps视频流的客户的，从192.168.1.100中获取视频流，并将它通过ros2话题发布出来，并可视化


先在示教界面再实现两个接口，完成对机器人上身的高度控制和头部转动的控制（接口参数存在命名混淆，按照描述的来）：
1. 腰部控制，waist_angle的范围是0-600：
```bash
ros2 service call /waist_control interface_pkg/srv/WaistControl "{waist_angle: 450.0, waist_speed: 20, reserve: 0}"
```
2. 头部控制，俯仰角的输入要控制在0-35：
```bash
# 头部偏转角
ros2 service call /ascend_control interface_pkg/srv/AscendControl "{ascend_pos: 100.0, ascend_speed: 20, reserve: 0}"
#头部俯仰控制
ros2 service call /head_control interface_pkg/srv/HeadControl "{head_angle: 30.0, head_speed: 10, reserve: 0}" 

```
然后针对控制系统，开发一套任务编排模式：
任务类型：
1. 移动：两种模式：直接调用导航的接口，进行点位/路径移动
2. 上肢：两种模式，一种为直接调用示教存储的点位，能通过movej和movep进行运动，另一种为输入参考坐标系和末端位置姿态，进行movep运动
3. 上身：包含上身上下运动与头部转动
4. 夹爪：包含开闭合功能
5. 视觉：输入场景，输出抓取坐标位置，供上肢movep使用
6. sleep
此任务编排用于单元化机器人的工序，例如：
- 接受调度系统的指令抓取工序包含：移动到A点进行抓取，包含导航移动，上肢的预设点位移动，手部相机的抓取位置识别，movep到抓取位置，夹爪闭合，手臂移动到预设位置
对上层的调度系统，需要提供get方法获取全部已经编排好的工序，执行工序的post方法需要提供导航点位的输入（只有调度系统知道要去哪个点位进行工作）

需要做出以下修改
1. 工作流中上肢运动的坐标模式需要关联视觉的输出
2. 移动功能要兼顾调度系统的提供与手动选择通过导航接口获取的点位
3. 工作流列表的三列数据只占据了表格的左侧，填充满
4. 添加步骤中的选项为白底过于显眼，要求符合页面风格

新增视觉相关功能：
1. 后续要在机器人上配置3个奥比中光相机，由于暂未到货无法调试，先预留出ROS2的功能接口
2. 包含抓位姿的返回
3. 前端页面新增视频查询功能，能够获取到相机发布的原视频，灰度图，带框的视频等，为了避免长期占据带宽一次只能显示一个摄像头的一种视频流，需要点击连接后才显示，切到其他页面后断开连接

1. 工作流中的手动选择移动接口通过调用导航相关接口获取地图列表，导航点列表
2. 视觉关联做一下约束，只能选择工序在前面的

修复一下urdf,将机器人的上半身默认位置向下移动5cm,并在双臂的末端添加一个24cmx24cmx15cm的方块，用作描述夹爪的碰撞体积


接下来基于现有的控制系统功能和下面描述重构调度系统：
1. 调度系统不再负责直接向机器人的底盘导航直接发送指令
2. 调度系统的调度功能为获取机器人的工作流列表并调用机器人的工作流和对制样机的指令下发
3. 调度系统需要任务编排模块
4. 调度系统的任务编排有手动触发和基于L2系统的触发，与L2系统的对接暂时空出
5. 工作流运行时需要实时显示每个子任务的运行状态，需要同步机器人的子工作流，控制系统的子工作流每执行一次都要向调度系统上报，并进行日志存储
6. 机器人和制样机出现异常时，需要有报警记录和推送，推送接口暂时空出
7. 异常分为警告和严重，警告级别为一些参数的异常，仅记录。严重为工序执行出错，调度需立即停止工序
8. 现在调度系统的页面分为：
 - 状态显示：显示机器人的状态（手臂，底盘，加爪，电量等），制样机状态（细节待定）
 - 制样机控制: 功能待定
 - 任务编排
 - 任务执行：手动执行，监听执行，子任务状态显示实时更新，以及机器人子任务的直接调用
 - 报警页面
 - 运行日志
由于文档存在滞后性，阅读新的控制系统代码，判断哪些功能无法满足新的调度系统需求并补全，同时重构调度系统。调度系统的代码可以做删除重构，控制系统的代码只能做添加补充。
同时基于与控制系统的通讯接口，设计模拟的控制系统和制样机，向上发送随机装数据与模拟任务流。该模拟控制系统可以接受调度系统的任务指令，sleep后返回状态数据。同时设计随机异常数据返回，用于模拟实际的异常状况

1. 执行历史的模板改为名称
2. 添加日期
3. 添加日期排序搜索
4. 修改详情页面：跳出弹床，将模板底下全部子任务按照卡片形式拍成一排，显示，状态，执行时间等信息，用于直观的展现到了哪一步骤，之前的步骤用时多久，步骤执行状况等


现在我需要进行视觉模块的开发：
1. 相机使用的是奥比中光，ros2相关的sdk已经安装，你可以检查
2. pyhton_pkg中有些以前项目的视觉遗留模型，使用的是realsence相机，阅读代码逻辑，提供功能描述文档并将视频输入更改为奥比中光相机，后续视觉相关功能继续集成在python_pkg中
3. 实现一个用于获取三个相机的ros2话题并进行rviz的可视化（当前只有一个），提供调试用命令，集成进控制系统中的视觉可视化功能中。
4. 实现一个接口，输入为识别内容的字符串和相机id,输入为抓取位姿，读取参数和识别逻辑空出，将这个功能集成进控制系统的视觉相关功能中

问题描述：
1. 重新运行ros2 launch orbbec_camera orbbec_camera.launch.py camera_name:=camera_1原本可以显示的rviz又无法显示
2. 为避免三个相机同时发布话题冲爆网络带宽，设置话题发布开关请求
3. 将视觉的启动也接入控制系统的node manager
4. 对接控制系统的相机画面可视化


问题修复：
控制系统：
1. 更新位置信息，电量，当前地图，充电状态获取，通过调用底盘接口
- 状态获取的接口为：/real_time_data/robot_hardware_status, 具体响应查看：docs/Magic商业导航接口-v1.4.4.json，询问频率为1s
调度系统：
1. 状态显示全面同步控制系统
2. 任务编排工作流获取同步到部署环境，对接实际的控制系统而不是仿真


控制系统页面优化：
1. 手臂运控页面改名为上身运控
2. 上身运控仅保留使能状态，上身控制，点动控制三个卡片，示教管理卡片移动
3. 点动控制卡片的手臂，模式右侧添加两个按钮，示教管理和点位保存
4. 点位保存点击后跳出窗口，输入名称，同时直接保留当前点动控制页面下的手臂选择和模式选择
5. 点击示教管理按钮，跳出大弹窗列表，依次为名称，手臂，角度，末端坐标，运动模式，操作。
6. 操作下面为三个功能按钮，执行，更新，删除
7. 运动模式默认为存储时的模式，例如在moveJ模式下，存储点位，则默认为moveJ,执行按钮将按照moveJ执行。
8. 支持按照手臂筛选


1. 工作流执行的结果展示额外添加一个按钮查看，这样在展示期间可以切换到其他页面
2. 对于工作流的子任务执行也都要进行日志记录，什么时候执行了什么步骤，结果如何等
3. 后台日志的查询自动跳转到底部


添加对机器人电机机构的状态监控和显示：
订阅ros2话题motor_feedback：
angle: -38.869998931884766
pos: 30
waist_err: 1
ascend_err: 0
waist_ready: 2
ascend_ready: 2
waist_temp: 29
ascend_temp: 0
waist_current: 0
ascend_current: 0
head_back_angle: 13.518528938293457
head_flag: 1
其中：
- angle代表头部偏转角度
- pos/100为升降机该度
- head_back_angle为头部俯仰角度
其余的信息可以忽略

现在我需要开发双臂规划控制功能：
1. 检查t1_moveit_config的配置文件，确认双臂规划组已经配置
2. 阅读t1_moveit_control_service.cpp代码，仿造左臂和右臂规划组，完成双臂规划组的代码编写
3. 在控制系统上肢运动的示教管理中，添加组合功能，能够将一组左臂数据和右臂数据进行组合，并新增手臂“双臂”
4. 在单步测试工作流编排中，上肢运控/手臂选项添加双臂，若模式为坐标，针对每一个手臂都能设置参考坐标系和视觉输出坐标