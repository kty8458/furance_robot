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
