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


1. 示教管理添加功能，将两个单臂的moveJ点位组合为双臂的moveJ点位
2. 修复点动控制中双臂moveJ的数据错误：{
    "detail": [
        {
            "type": "value_error",
            "loc": [
                "body"
            ],
            "msg": "Value error, moveJ requires joint_angles",
            "input": {
                "arm": "right",
                "method": "moveJ",
                "coordinate": "base_link",
                "position": {
                    "x": 702.678,
                    "y": -605.6531446386047,
                    "z": 577.1589322697802,
                    "roll": -68.0593705528902,
                    "pitch": -14.29890266096374,
                    "yaw": 23.058459332653396
                }
            },
            "ctx": {
                "error": {}
            }
        }
    ]
}
3. 修改工作流中的双臂执行逻辑，moveJ方法中通过勾选选项来 决定是分别执行两个单臂的moveJ点位还是双臂的点位
4. 检查moveit的双臂规划组，和机器人urdf结构，修复moveit初始化的bug，判断能否完成双臂moveP规划：
[move_group-5] [INFO] [1781051801.039235965] [moveit_cached_ik_kinematics_plugin.cached_ik_kinematics_plugin]: cache file /home/kty/Desktop/furance_robot/ros2_ws/t1right_arm_SJ_LinkARM-R-J7_Link_5000_1.000000_1.000000.ikcache initialized!
[move_group-5] [ERROR] [1781051801.039254682] [moveit_kinematics_base.kinematics_base]: Group 'both_arm' is not a chain
[move_group-5] [ERROR] [1781051801.039261806] [kinematics_plugin_loader]: Kinematics solver of type 'cached_ik_kinematics_plugin/CachedKDLKinematicsPlugin' could not be initialized for group 'both_arm'
[move_group-5] [ERROR] [1781051801.039274098] [moveit_ros.robot_model_loader]: Kinematics solver could not be instantiated for joint group both_arm.
5. 修复插件加载bug：
[move_group-5] [INFO] [1781051807.134869276] [moveit_ros.planning_scene_monitor.planning_scene_monitor]: Listening to 'planning_scene_world' for planning scene world geometry
[move_group-5] [WARN] [1781051807.135155062] [moveit.ros.occupancy_map_monitor.middleware_handle]: Resolution not specified for Octomap. Assuming resolution = 0.1 instead
[move_group-5] [ERROR] [1781051807.135173151] [moveit.ros.occupancy_map_monitor.middleware_handle]: No 3D sensor plugin(s) defined for octomap updates
[move_group-5] [WARN] [1781051837.786807290] [moveit_ros.planning_scene_monitor.planning_scene_monitor]: It is likely there are too many vertices in collision geometry
[move_group-5] [INFO] [1781051842.340997421] [moveit.ros_planning_interface.moveit_cpp]: Loading planning pipeline 'move_group'
[move_group-5] [INFO] [1781051842.372206649] [moveit.ros_planning.planning_pipeline]: Using planning interface 'OMPL'
[move_group-5] [ERROR] [1781051842.373243567] [moveit.ros_planning.planning_pipeline]: Exception while loading planning adapter plugin 'default_planner_request_adapters/AddTimeOptimalParameterization
[move_group-5] ': According to the loaded plugin descriptions the class default_planner_request_adapters/AddTimeOptimalParameterization
[move_group-5]  with base class type planning_request_adapter::PlanningRequestAdapter does not exist. Declared types are  default_planner_request_adapters/AddRuckigTrajectorySmoothing default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/Empty default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/ResolveConstraintFrames
[move_group-5] [ERROR] [1781051842.373292665] [moveit.ros_planning.planning_pipeline]: Exception while loading planning adapter plugin 'default_planner_request_adapters/FixWorkspaceBounds
[move_group-5] ': According to the loaded plugin descriptions the class default_planner_request_adapters/FixWorkspaceBounds
[move_group-5]  with base class type planning_request_adapter::PlanningRequestAdapter does not exist. Declared types are  default_planner_request_adapters/AddRuckigTrajectorySmoothing default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/Empty default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/ResolveConstraintFrames
[move_group-5] [ERROR] [1781051842.373306563] [moveit.ros_planning.planning_pipeline]: Exception while loading planning adapter plugin 'default_planner_request_adapters/FixStartStateBounds
[move_group-5] ': According to the loaded plugin descriptions the class default_planner_request_adapters/FixStartStateBounds
[move_group-5]  with base class type planning_request_adapter::PlanningRequestAdapter does not exist. Declared types are  default_planner_request_adapters/AddRuckigTrajectorySmoothing default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/Empty default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/ResolveConstraintFrames
[move_group-5] [ERROR] [1781051842.373319064] [moveit.ros_planning.planning_pipeline]: Exception while loading planning adapter plugin 'default_planner_request_adapters/FixStartStateCollision
[move_group-5] ': According to the loaded plugin descriptions the class default_planner_request_adapters/FixStartStateCollision
[move_group-5]  with base class type planning_request_adapter::PlanningRequestAdapter does not exist. Declared types are  default_planner_request_adapters/AddRuckigTrajectorySmoothing default_planner_request_adapters/AddTimeOptimalParameterization default_planner_request_adapters/Empty default_planner_request_adapters/FixStartStateBounds default_planner_request_adapters/FixStartStateCollision default_planner_request_adapters/FixStartStatePathConstraints default_planner_request_adapters/FixWorkspaceBounds default_planner_request_adapters/ResolveConstraintFrames

bug修复：
1. 双臂示教点位执行报错：
    {arm: "both", name: "both_zero_pose"}
    arm
    : 
    "both"
    name
    : 
    "both_zero_pose"
2. 双臂示教点位展示错位，要求左臂在上右臂在下：
J1-J7
角度数据
xyzrpy 坐标系
pose数据+坐标系
3. 
工作流中的改动有问题，如果不勾选，则是将两个单臂轨迹整合一起执行，如果勾选，则隐藏两个单臂选择，列出双臂的点位存储列表

参考奥比中光pysdk的文档：https://orbbec.github.io/pyorbbecsdk/source/3_QuickStarts/QuickStart.html#no-device-found-linux
帮我在在ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision路径下实现一个使用奥比中光的example用例，用于获取摄像头信息，以及彩色，深度视频流的显示

现在相机example已经实现，以此为基准对接机器人控制系统开发后续功能：
1. 当前仅连接了一个摄像头，后续计划连接三个（头，左手，右手）。使用配置文件的方式将三个相机与三个位置进行绑定，方便后续调整
2. 开发获取摄像头信息的接口提供给控制系统后端调用，对接前端的相机页面，和工作流页面，能够选择相机
3. 基于前端相机页面的视频类型功能，添加选择视频类型支持原始画面，深度画面，以及后续开发中带有识别框的画面三类
4. 点击连接后，将对应的视频数据推送到页面中
5. 提供视频数据获取的方法，供后续进行视觉算法开发时使用


优化状态健康页面，颗粒度拆细：
1. 底盘，上身，上肢，夹爪，相机分别拆分卡片
2. 底盘当前状态包括位置，地图，电量，充电状态，新增错误码（接口参数为：error，0为正常）与状态（接口参数为current_working，1 未运行, 2 扫地图, 3 导航启动, 4 正在执行导航（刚启动导航时是3，执行导航中是4，执行完导航任务后为1），未获取到数据则显示离线），
3. 上身状态包括头部偏转，头部俯仰，升降高度,新增状态，当未收到状态数据测显示离线
4. 上肢包括左手状态与右手状态，使能状态，新增错误状态的显示
5. 夹爪数据重构，新增当前力矩，移动距离，温度，和连接状态，当前未确认夹爪接口，仅作保留
6. 新增相机卡片，显示三个相机的连接状态

1. 页面布局优化，每行两列卡片
2. 相机状态获取有问题，已经开启了相机节点并且头部相机连接中，点击刷新没有获取到正常状态。
3. 更改相机展示逻辑，左侧列出三个部位相机，右侧显示连接状态


https://github.com/kty8458/furance_robot.git
1. 代码克隆到本地，开一个新分支
2. 新增视觉代码放进ros2_ws/src/t1_robot/python_pkgs/python_pkgs下
3. 新增ros2接口代码放入ros2_ws/src/t1_robot/control_interfaces下
视觉任务：
1. 使用棋盘格进行相机标定，获取到head_camera_link->tou_link，left_camera_link->ARM-L-J7_Link，right_camera_link->ARM-R-J7_Link的坐标变换，并发布tf话题，将完成流程集成化，方便后续法兰、头部连接件发生更改后快速标定
2. 标定数据可以一yaml或者json存入本地，tf的发布方式可以参考ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py文件中的tf2_ros节点
3. 寻找视觉方案，识别取样杆的抓取6Dpose


现在在ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision中实现一个相机标定的代码，通过奥比中光的sdk获取到相机的内参与外参，通过棋盘格获取到相机的head_camear_link->tou_link的tf变换并发布。机器人的urdf模型在ros2_ws/src/t1_robot/t1_description下面。将获取到的内外参和变换存储在ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision/camera_config.yaml中


目前的项目结构是：
1. 运行ros2_ws/src/t1_robot/t1_moveit_config/launch/t1_moveit_headless.launch.py后，ros2_ws/src/t1_robot/python_pkgs/python_pkgs/t1_control/t1_joint_states_publisher.py会订阅机器人14轴的电机角度和上身机构的角度，并发布joint_state
2. robot_state_publisher会发布/tf话题
3. ros2_ws/src/t1_robot/python_pkgs/python_pkgs/orbbec_vision/camera_calibration.py是从其他地方移植的相机标定代码
目标是通过相机标定代码，获取到head_camera->tou2_link, left_camera_link->ARM_L7_Link, right_camera_link->ARM_R7_Link的坐标变换并发布进tf话题，供后续的抓取识别算法使用获取双臂运动规划器能直接使用的抓取位姿
目前正在将棋盘各固定在左手末端，获取head_camera->tou2_link的静态变换，并将变换存入yaml文件。
阅读camera_calibration.py代码，确认它能否满足功能需求

控制系统相机模块改进：
1. 保留现有的ROS2节点启动推流，新增红外灰度图像的推送
2. 读取config标定完成的yaml文件，发布相机到末端的tf变换
3. 参考/home/kty/Desktop/furance_robot/ros2_ws/src/t1_robot/python_pkgs/python_pkgs/vision下面的一些视觉工具代码，完成：
    - 二维码与相机的坐标识别，获取到二维码与相机之间的变换矩阵，支持彩色和红外的图像识别，并支持将带识别二维码坐标轴的画面也推送到前端
    - 通过二维码和tf话题中发布的末端姿态，求出当前末端位置与二维码的变换矩阵，并存储（用于现场的机械臂标定，二维码与工作位置相对固定）
    - 标定功能封装为接口，供机器人控制系统的后台调用，在前端页面的相机页面中添加功能，通过勾选相机和手臂求出变换矩阵并存入config文件
    - 控制系统的工作流编排功能的相机模块，输入为相机，功能，场景。其中相机保持不变; 功能分为二维码，和视觉模型，视觉模型暂未开发保留接口;场景则获取每个功能对应的yaml文件，通过下拉框获取到yaml文件中存入的标定点位或者视觉模型。通过三个参数完成目标位姿的计算，例如输入为right_camera,二维码，放置点，请求发送后视觉模块会读取之前标定过的二位码与放置点的坐标变换，再通过当前相机识别到的与二维码之间的变换，求出可以提供给机械臂移动的位姿。
    - 优化工作流上肢中的坐标模式，添加偏移功能。因此它的xyzrpy输入应该分为2排，第一排为输入，第二排为偏移。在第二排添加勾选参考base link和tool link下的偏移功能（默认为baselink。基于左臂还是右臂判断是哪只手的末端）
    参数输入分为三种：
        1. 当前逻辑，全为空白直接填写
        2. 获取当前参考坐标系下的末端姿态填入输入，然后基于baselink和toollink的选择进行偏移输入。例如将当前的末端沿baselinkz轴移动10mm,或者沿着末端的x轴方向移动10mm
        3. 关联视觉后将视觉求出的姿态填入第一排的输入，第二排为偏移。此功能用于方便视觉识别抓取后将物体抓起或者拿出。
    - 每一个功能一个py代码，由camera_manager_node统一调用。视觉识别出的结果记录要详细的日志，方便后续调试


我现在要检查二维码识别的效果。我使用了一个tag36h11 id=1 8cm的二维码。现在将qr_detector.py的功能集成进test_ir_chessboard.py，同时展现彩色检测和红外就检测的结果，将坐标轴和变换矩阵也实时打印在图像输出上面，并关闭棋盘各的检测。


问题修复：
1. 相机下拉框获取到三个相机后没有办法选择，勾选被禁用
2. 当前仅只有一个右臂相机，但是下拉框却出现了三个相机，且默认为头部相机，勾选头部相机后点击连接也没有报错，请求表示正常

问题修复：
1. 相机画面的现场标定功能中没勾选红外或者色标定的框
2. 执行标定的时候接口超时，相机节点报

重构相机画面的交互逻辑：
1. 页面分为两部分，上下切割。
2. 上部分为相机选择窗口+视频显示窗口
3. 下部分为现场标定窗口，修改交互逻辑：
    - 分为两部分，第一部分为场景的增删查改，相机勾选，手臂勾选，新建场景，新建点位，查看点位，修改点位，删除点位等功能。
    - 点位创建后直接以空的数据写入yaml功能。
    - 点击点位后展示存储的xyzryp数据，可以直接进行手动修改并更新
    - 第二部分为视觉标定，添加场景下拉框和点位下拉框，勾选后自动读取相机，手臂等参数。在此处设置视频流，QRID和QR尺寸参数，点击标定后更新当前点位数据

问题修复+优化：
1. 在修改后的相机页面现场标定模块中，在新建了场景-点位后没法获取到已经创建的点位列表，不管是在点位管理和视觉标定模块中
2. 修改场景 & 点位管理下的点位模式。在勾选了上面的场景后，点位将会出现一个表格，表格分为2列，点位名称和操作。操作有两种，编辑，删除。点击编辑后会跳出弹窗，显示当前点位存储的数据，包含场景（不可修改），名称（可修改），对应的手臂（下拉框），对应的相机（下拉框），使用的相机流（二选一），QRid（数值填写),QR尺寸（数值填写），标定后的变换（xyzrpy数值填写）。
3. 右侧视觉标定窗口，勾选了场景和标定点后下发会自动出现对于点位编辑的表格（除了变换），点击标定后会将在此编辑过的数据以及求出的变换存入当前点位


问题修复：
1. 在工作流中执行二维码视觉识别的时候报错：Service /vision_detect not available
2. 开启视频流后二维码检测可能存在坐标跳变的现象，按照当前计算误差的区间平均值设定为标定的数据和工作流中视觉检测的数据

问题修复：
经过检测，qr_calibrator.py的标定逻辑存在问题。标定的本质其实是以qr码作为不动的参照物，求出机械臂末端应有的位置。因此在第四步：
    # 4. T_qr_workspace = inv(T_ee_qr) (末端对准工作位置)
    T_qr_workspace = np.linalg.inv(T_ee_qr)
    logger.info("calibrate: T_qr_workspace = inv(T_ee_qr) =\n%s", T_qr_workspace)
存储的数据毫无意义，函数的输入需要加入T_base_ee变量，然后求出qr与base的变换并存储。这样在后续的识别中能够求出在base link的位置发生变化后机械臂末端应该到的位置。其中T_base_ee可以订阅tf话题获取baselink与ARM-R-J7_Link和ARM-L-L7_Link
TF的订阅可以放到外面，调用函数的输入输入T_base_ee即可

target_pose x=0.6619 y=-0.2540 z=0.5396 roll=0.0670 pitch=0.1564 yaw=-0.1091
target_pose x=0.7028 y=-0.3394 z=0.3764 roll=-0.2762 pitch=-0.0086 yaw=-0.0140

target_pose x=711.7936 y=-362.8852 z=374.2360 roll=-17.9988 pitch=-1.4127 yaw=-0.1135

target_pose x=616.3773 y=-324.8218 z=556.8071 roll=-3.8913 pitch=12.9142 yaw=-4.8427

target_pose x=698.8688 y=-339.0147 z=377.8105 roll=-15.8242 pitch=-0.0811 yaw=-0.8938
target_pose x=698.8415 y=-339.0949 z=377.8246 roll=-15.8323 pitch=-0.0827 yaw=-0.8908

target_pose x=698.8345 y=-339.0967 z=377.8178 roll=-15.8323 pitch=-0.0817 yaw=-0.8910

检查一下每次检测视觉获取到的帧是不是实时的，还是获取到了之前的残留帧画面。求解出的坐标数据对不上


target_pose x=622.0035 y=-330.0210 z=544.8664 roll=-3.7588 pitch=11.9982 yaw=-4.0642
target_pose x=624.2220 y=-331.6923 z=543.2832 roll=-3.9279 pitch=11.7227 yaw=-4.0704

target_pose x=619.8658 y=-337.9549 z=544.9526 roll=-4.7774 pitch=12.1786 yaw=-4.2871

target_pose x=729.8489 y=-323.8655 z=371.3267 roll=-14.5292 pitch=-2.3719 yaw=-0.6382


target_pose x=663.3952 y=-336.4529 z=511.7411 roll=-3.9179 pitch=8.2465 yaw=-4.4607

698.9
-339.0
377.8
-15.8°
-0.1°
-0.9°
base_link


[orbbec_vision.camera_manager INFO] compute_pose: loaded point 'test3' from scene '测试1': arm=right qr_ids=[] marker_size=0.085 stream_type=color
[06/24 16:47:37.955260][info][391065][Pipeline.cpp:228] [CPC9363000DA] Check and set config done!
[06/24 16:47:37.955713][info][391065][Pipeline.cpp:266] [CPC9363000DA] Try to start streams!
[06/24 16:47:37.955768][info][391065][VideoSensor.cpp:58] [CPC9363000DA] Try to start stream: {type: Color, format: MJPG, width: 1280, height: 720, fps: 30}
[06/24 16:47:37.955791][info][391065][SensorBase.cpp:210] [CPC9363000DA] Stream state changed from STOPPED to STARTING@Color
[06/24 16:47:37.955804][info][391065][VideoSensor.cpp:127] [CPC9363000DA] Start backend stream: {type: Color, format: MJPG, width: 1280, height: 720, fps: 30}
[06/24 16:47:37.957672][info][391065][Pipeline.cpp:293] [CPC9363000DA] Start streams done!
[06/24 16:47:37.957694][info][391065][Pipeline.cpp:250] [CPC9363000DA] Pipeline start done!
[orbbec_vision.camera_manager INFO] Stream started: right_arm type=raw need_color=True need_depth=False need_ir=False
[06/24 16:47:38.058074][warning][393864][Pipeline.cpp:335] [CPC9363000DA] Wait for frame timeout, you can try to increase the wait time! current timeout=100
[06/24 16:47:38.437192][info][393863][VideoSensor.cpp:153] [CPC9363000DA] Color backend frame callback, frameRate=0.073657fps
[06/24 16:47:38.437260][info][393863][SensorBase.cpp:210] [CPC9363000DA] Stream state changed from STARTING to STREAMING@Color
[06/24 16:47:38.437573][info][393866][SensorBase.cpp:379] [CPC9363000DA] Color Streaming... frameRate=0.073657fps

[orbbec_vision.camera_manager INFO] Stream stopped: right_arm (pipeline preserved)
[orbbec_vision.camera_manager INFO] compute_pose: collected observations from 2 QRs over 10 frames
[orbbec_vision.camera_manager INFO] TF lookup base_link→ARM-R-J7_Link: trans=[0.7101, -0.4246, 0.5314]
[orbbec_vision.camera_manager INFO]   QR id=4 (10 obs, area=6020): t=[0.6520,-0.3678,0.5134]
[orbbec_vision.camera_manager INFO]   QR id=5 (10 obs, area=6487): t=[0.6740,-0.3073,0.5102]
[orbbec_vision.camera_manager INFO] compute_pose: fused 2 QRs (weights=['0.48', '0.52'])
[orbbec_vision.camera_manager INFO] compute_pose: result T_base_ee_target → xyz(m)=[0.6634,-0.3365,0.5117] rpy(rad)=[-0.0684,0.1439,-0.0779]
[orbbec_vision.camera_manager INFO] compute_pose: output (mm+deg) → xyz=[663.40,-336.45,511.74] rpy=[-3.92,8.25,-4.46]
[06/24 16:47:41.168752][warning][393865][Pipeline.cpp:335] [CPC9363000DA] Wait for frame timeout, you can try to increase the wait time! current timeout=100 [**3 logs in 3110ms, last: 16:47:38.389043**]


[orbbec_vision.qr_calibrator INFO] calibrate: T_camera_ee (from config)=
[[ 0.99999853 -0.00125209 -0.00117559 -0.07258206]
 [ 0.00124951  0.99999682 -0.0021927   0.09151272]
 [ 0.00117833  0.00219123  0.99999691 -0.01274688]
 [ 0.          0.          0.          1.        ]]
[orbbec_vision.qr_calibrator INFO] calibrate: QR id=4 (20 frames) → T_qr_ee t=[0.05148568725310524, 0.19536148930224148, 0.7495600591672016] r=[-0.14158990829238324, 0.9870560101318944, 0.050257815736879645, 0.05609708271931966]
[orbbec_vision.qr_calibrator INFO] calibrate: QR id=5 (20 frames) → T_qr_ee t=[0.1676601666138034, 0.22615412695949763, 0.7379720923176624] r=[-0.13679017875361235, 0.9889894497463844, 0.02855699430377256, 0.048711532138016884]


检查一下点位的坐标转换计算是否存在问题。我当前的测试流程为：
1. 在point1标定点位test3
2. 进入工作流直接执行视觉识别
3. 识别结果接近当前的位置，误差在可接受范围内：
[orbbec_vision.camera_manager INFO] TF lookup base_link→ARM-R-J7_Link: trans=[0.6989, -0.3390, 0.3778] rpy(deg)=[-15.82, -0.08, -0.89] quat(xyzw)=[-0.1376, 0.0004, -0.0078, 0.9905]
target_pose x=701.9188 y=-343.3650 z=375.9896 roll=-16.1097 pitch=-0.3353 yaw=-0.7759
4. 移动到point2
5. 使用test3进行视觉识别，期望输出结果为接近point1原点位TF lookup base_link→ARM-R-J7_Link
6. 但是结果误差很大：
[orbbec_vision.camera_manager INFO] TF lookup base_link→ARM-R-J7_Link: trans=[0.7098, -0.4241, 0.5305] rpy(deg)=[-6.95, 8.58, 3.31] quat(xyzw)=[-0.0626, 0.0729, 0.0332, 0.9948]
target_pose x=631.6354 y=-310.5582 z=536.7116 roll=-2.0350 pitch=11.2767 yaw=-4.9314
排查下计算过程和可能的原因

实际位置：
[orbbec_vision.camera_manager INFO] TF lookup base_link→ARM-R-J7_Link: trans=[0.6989, -0.3390, 0.3778] rpy(deg)=[-15.82, -0.08, -0.89] quat(xyzw)=[-0.1376, 0.0004, -0.0078, 0.9905]
两次标定的位置：
target_pose x=702.1766 y=-330.9218 z=373.4763 roll=-15.7094 pitch=-0.4102 yaw=-1.4600
target_pose x=700.9554 y=-365.9374 z=341.1807 roll=-15.5858 pitch=-2.0249 yaw=1.6813
误差变小，总结下为什么标定脚本没有考虑到相机的朝向

现在添加导航模块的定距离定角度工程：
1. 详细接口说明为：
4.7.3 定距离定角度移动控制
Method：POST
URL：/cmd/move_with_params
Body：
{
"linear_velocity": 0.2, // x轴线速度（m/s 范围-0.5到0.5）
"slip_angle": 0.78, // 四转四驱底盘侧偏角（rad 范围-2.14到2.14）
"angular_velocity": 0.2, // 角速度（rad/s 范围-0.5到0.5）
"target_distance": 2, // 目标距离（m）
"target_angle": 3.14, // 目标角度（rad 范围0到3.14）
"mode": 1 // 模式标志：1=定距离移动，2=定角度移动
}
响应示例：
{
"data": null,
"errCode": 0,
"msg": "Fixed distance movement completed",
"successed": true
}
说明：
两种模式，直线定距离行驶、原地定角度旋转。差速底盘和四转四驱底盘两种模式都有，阿克曼底盘只有直线定距离行驶，四
转四驱底盘在直线定距离行驶模式下，可以使用横移模式。
直线定距离行驶模式下，angular_velocity、target_angle的值不会生效；原地定角度旋转模式下，linear_velocity、
slip_angle、target_distance的值不会生效。
对于四转四驱底盘，当侧偏角slip_angle不为0时，将使用横移模式，行驶目标距离。
使用该接口时，确保小车定位准确
2. 在导航页面的中新增定角度定距离控制的卡片，完成对上述参数设置与下发，模式选择使用勾选，默认为定距离
3. 在卡片中添加取消控制的按钮，接口为：
    4.7.4 取消定距离定角度移动控制
    Method：POSTURL：/cmd/cancel_move_with_params
    Body：
    {
    "cancel": true
    }
    响应示例：
    {
    "data": null,
    "errCode": 0,
    "msg": "取消移动指令发布成功",
    "successed": true
    }
    说明：
    调用定距离定角度移动控制接口后，如果不想继续行驶，需要调用该接口取消。
4. 将定距离定角度运动也添加到工作流的移动功能中，将当前的点位来源名称修改为运动模式，将“调度系统提供”直接改为“调度系统”，新增选项定距离定角度移动控制，将上述的接口集成进工作流的设置中。
5. 取消工作流的接口添加取消定距离定角度移动控制的指令下发


现在有一个组网的问题。我的成套机器人上有一个交换机，局域网组的是192.168.1网段。交换机连接了一个路由器，连接了现场的wifi,wifi下有一个局域网，走而是192.168.8网段。现在我使用了一个平板连接了现场的机器人，想直接访问机器人底盘的192.168.1.2ip,应该怎么做

现在有一个组网的问题。我的成套机器人上有一个路由器，它集成了导航工控机和激光雷达的网络通讯。我现在有另一套组网设备，包含了一个交换机和一个路由器，集成了我的主控电脑和手臂的上肢控制工控机。现在我将底盘的路由器和上肢相关的交换机使用网线连接，出现了问题，底盘的激光雷达数据无法正常传输。如何排查网络的路由问题


我现在要编写开机自启动的脚本和系统服务文件。
控制系统自启动需要的有三个：
1. furance_sim 下的node_namager节点，用于管理其他ros2相关节点的启动，运行需要source ~/.bashrc,核心环境变量为：
export ROS_DOMAIN_ID=45
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export CYCLONEDDS_URI=file://$HOME/.ros/cyclonedds_profile.xml
以及source ros2_ws下的install/setup.bash加载包信息
2. robot_control/backend下运行 ROS2_MODE=real python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000，由于后台也涉及到ros2通讯，node_namager启动所需的环境变量后台也需要加载。同时后台使用的python环境为系统环境
3. 先将robot_control/frontend下的前端页面服务编译为server版本非dev,然后自启动需要运行npm run server。
然后你需要将生成的系统脚本和服务放入scripts文件夹下面，并提供一个一次性安装脚本，运行后自动安装systemctl文件到指定位置并启动

现在ros2_ws下面新增了一个包grippers_control，这个包是使用modbus控制电动夹爪，和最终的选型不同。现在需要临时使用，将包进行以下需求修改：
1. 将action控制修改为service控制，接口请求数据保持一样
2. 核心代码在grippers_action_server.py中
3. service接口编译进control_interface中
4. 整个控制包并入python 
5. 测试使可能只连接一个夹爪，不要因为减少一个夹爪而影响服务的启动
接下来涉及夹爪模块集成到控制系统：
1. node_manager注销之前的夹爪预留节点，添加这个节点，改名为modbus_gripper
2. 页面中上身运控的左侧栏目添加卡片：夹爪控制，能够通过分别设置两个夹爪的力矩和位置，控制夹爪的开合闭合
3. 工作流编排中集成夹爪任务编排，涉及参数输入为左右/力矩/位置（力矩位置输入范围均为0-100）
接下来需要优化工作流的执行逻辑：
1. 添加手动执行模式，在手动执行模式下每执行一步后会等待指令，点击下一步后才会继续执行
2. 手动执行模式下，需要能够对未执行步骤的参数进行修改
3.  为了避免工作流编排过长，添加隐藏参数的按钮，对于已经编辑完的工序隐藏其详细信息，仅保留任务类型和名称

机器人上身运动的控制板重新更换，实际接口的变量描述与实际控制正常匹配。
现在修复一下控制系统中关于腰部升降与头部偏转的调用逻辑，将二者交换

优化一下工作流编排的操作逻辑：
1. 重构一下工作流的页面，改为上下2部分，上部分为目前的工作流列表窗口，保留新建刷新选择等功能，但缩短为一行固定在上方。获取工作流列表更改为点击后出现弹窗，再进行选择删除等操作。
2. 添加步骤固定在下部分的左侧，防止工作流过长每次添加后要重新拉回上方
3. 为右侧工作流的每一个工序添加选择的属性（单选，表明当前选择的步骤），后续添加心的步骤后从添加进选择的下方，减少往前添加工序的操作
4. 添加工序复制功能，点击复制后往工作流最底下添加一个相同参数的工序
5. 添加工作流复制功能

当前情况是上身控制的控制版出现了异常。更换控制版需要时间，为了不影响进度采取两手准备
1. 合并当前分支到主分支，删除当前分支
2. 重新创建新分支，用于自己开发上身运控
已知信息和需求如下：
1. 上身运控使用的是opencan通讯协议，但具体的报文电文格式之类的还不清楚
2. 需要自己开发的功能按照当前的接口来，依然包含状态监控读取，升降机的控制与头部的俯仰、偏转
3. 新的控制逻辑还是以ros2节点的形式启动，放入python_pkg下面，通过node manager进行启动管理
4. 相关控制接口与现在interface_pkg有关上身的service和topic数据内容保持一致，但是编译放到control_interfaces中，用于区分但是尽量减少修改
5. 需要能够兼容控制版控制与ros2节点直接控制
6. 需要考虑到ubutu设备上can口相关的初始化步骤

修复一下modbus夹爪的问题。当串口线更换了usb接口后，可能出现/ttyUSB0-9的任意串口序号。每次重启自动搜索存在的串口号而不是手动指定


我现在要探索一个新的功能，通过机械臂末端的深度相机识别物体获取抓取位姿，场景描述如下：
1. 抓取目标物体是一个长杆子，可以视为一个圆柱体
2. 长杆子躺在一个滑槽中，有部分露出
3. 场景光线较为昏暗，长杆温度可能较高
跟我沟通探寻一下有什么现成的视觉算法可以使用，同时判断能否集成进机器人的控制系统：
1. 视觉模块需要能够提供深度图
2. moveit要能够获取到点云/深度信息对场景进行建模
3. 基于和特殊的抓取条件获取到抓取前的位姿（例如抓取杆子靠上的部分等）
4. 获取抓取前的位姿后能够执行moveL功能，末端走直线进入抓取点
5. 整套功能依然需要保持各个模块的独立性，同时需要能够集成进控制系统

经过一段时间使用，在使用工作流和示教点功能时，存在以下问题：
1. 每次选中一个工作流后有其他的需求退出到了其他页面，再次进入后需要重新选择工作流，并且当yaml文件偏大时前端页面加载较慢
2. 示教点位偏多后，选择起来困难。
3. 工作流在自动执行期间，如果切换到了其他页面，会中断对其的子任务监控
4. 执行到一个步骤后发现需要调整，停止工作流后需要重新执行整个工作流
因此交互逻辑需要优化：
1. 示教点存储逻辑修改，分为全局点位和工作流点位。全局点位每个工作流都可以共享，例如机械臂初始点之类的，工作流点位则只在当前工作流中显示
2. 操作流程优化，进入页面后默认无工作流，此时示教点位全部存储进全局点。勾选工作流后，示教点位的获取与存储全都基于当前工作流（包括工作流编排中的上肢运动点位选取）
3. 工作流选择后，切换到其他的页面后再次进入要保留当前的信息，避免重复加载。同时也要避免数据没有更新
4. 支持从中间步骤开始执行后续工作流，但是要注意视觉模块的兼容（有些上肢运动的点位是基于之前的视觉步骤）
同时，工作流执行要添加新的功能：
1. 循环执行，勾选一个工作流后回一直循环执行，可以设定循环间隔
