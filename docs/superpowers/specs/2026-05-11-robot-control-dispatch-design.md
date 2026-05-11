# 轮式双臂机器人控制系统与调度系统设计文档

## 1. 项目概述

### 1.1 背景

设计一套轮式双臂机器人的控制系统和现场调度系统，分别部署在工控机（Ubuntu 22.04）和控制柜（Win10）上，实现机器人的远程控制、状态监控、任务编排和制样机协同。

### 1.2 系统定位

| 子系统 | 部署位置 | 定位 |
|--------|----------|------|
| 机器人控制系统 | Ubuntu工控机 | 硬件代理层，封装ROS2接口，对外暴露HTTP/WS统一接口 |
| 调度系统 | Win10控制柜 | 业务逻辑层，任务编排、多机调度、制样机协同 |

### 1.3 约束

- 实际1台机器人，按2-5台设计以支持后续项目
- 1台制样机，机器人仅负责物流转运
- 机器人与制样机协作：机器人将样品送至制样机入口，制样机自动完成取放
- 手臂运控和示教功能仅在控制系统上使用
- L2系统接口协议待定，预留抽象层

---

## 2. 技术选型

| 项目 | 选型 | 说明 |
|------|------|------|
| 后端框架 | FastAPI | 两个系统统一 |
| 前端框架 | Vue 3 + Vite | 功能性优先 |
| 数据库 | SQLite（调度系统） | 本地轻量存储 |
| ROS2通讯 | ROS2 Service | 控制系统与执行节点交互 |
| 控制通讯 | HTTP | 调度→控制，下发指令 |
| 状态上报 | WebSocket | 控制→调度，单向推送 |
| 制样机通讯 | WebSocket | 调度为客户端，制样机为服务端 |
| 打包部署 | PyInstaller单包 | 可执行文件+静态资源 |
| 进程守护 | systemd(Ubuntu) / nssm(Win10) | 开机自启+崩溃重启 |

---

## 3. 架构设计

### 3.1 整体架构 — 分层代理

控制系统作为机器人的"代理层"，封装所有ROS2接口，对调度系统暴露统一的HTTP/WS接口。调度系统不直接感知ROS2。

```
调度系统 (Win10)                    控制系统 (Ubuntu)
  ┌──────────────┐                   ┌──────────────┐
  │ 调度页面      │                   │ 控制页面      │
  └──────┬───────┘                   └──────┬───────┘
         │ HTTP                           │ HTTP + WS(log)
  ┌──────┴───────┐                   ┌──────┴───────┐
  │ FastAPI后端   │◄──HTTP(指令)────│ FastAPI后端    │
  │  (SQLite)    │───WS(状态)────►│               │
  └──┬──┬────┬───┘                   └──────┬───────┘
     │  │    │                              │
     │  │    └──WS──► 制样机                 └──ROS2 Service──► ROS2节点群
     │  └──[预留]──► L2系统
     └──HTTP──► 控制系统
```

### 3.2 代码结构 — Monorepo

```
furance_robot/
├── shared/                      # 共享代码（Python包）
│   ├── models/                  # 通用数据模型（状态枚举、指令结构）
│   ├── protocol/                # 电文协议定义（WebSocket帧、HTTP Schema）
│   └── utils/                   # 通用工具（日志、异常）
│
├── robot_control/               # 机器人控制系统（Ubuntu工控机）
│   ├── backend/                 # FastAPI后端
│   │   ├── app/
│   │   │   ├── api/             # HTTP路由
│   │   │   ├── ws/              # WebSocket端点
│   │   │   ├── ros2/            # ROS2 Service客户端封装
│   │   │   ├── services/        # 业务逻辑
│   │   │   └── core/            # 配置、日志、生命周期
│   │   └── pyproject.toml
│   ├── frontend/                # Vue 3 + Vite
│   │   ├── src/
│   │   └── package.json
│   └── deploy/                  # 打包部署脚本
│
├── dispatch/                    # 调度系统（Win10控制柜）
│   ├── backend/                 # FastAPI后端
│   │   ├── app/
│   │   │   ├── api/             # HTTP路由
│   │   │   ├── ws/              # WebSocket客户端
│   │   │   ├── task/            # 任务编排引擎
│   │   │   ├── services/        # 业务逻辑
│   │   │   └── core/            # 配置、日志、生命周期
│   │   └── pyproject.toml
│   ├── frontend/                # Vue 3 + Vite
│   │   ├── src/
│   │   └── package.json
│   └── deploy/                  # 打包部署脚本
│
├── docs/                        # 文档
└── .claude/                     # Claude配置
```

---

## 4. 机器人控制系统详细设计

### 4.1 内部架构

```
前端 (Vue 3 + Vite)
  状态监控 | 指令面板 | 手臂运控 | ROS2管理 | 运行日志
      │        │ HTTP      │ HTTP     │ HTTP     │ WS(log)
      └────────┴───────────┴──────────┴──────────┘
                        │
后端 (FastAPI)
  API层: /api/v1/robot/{id}/... | /api/v1/maps/... | /api/v1/ros2/...
      │
  Service层: RobotService | ArmService | Ros2Manager | StatusService | LogService
      │
  ROS2 Bridge层: Ros2ServiceClient | Ros2TopicListener | Ros2LogCollector
      │
  WebSocket Server: /ws/v1/status(→调度) | /ws/v1/logs(→前端)
      │
  Supervisor: systemd service
```

### 4.2 组件职责

| 组件 | 职责 |
|------|------|
| Ros2ServiceClient | 封装所有ROS2 Service的异步调用，统一错误处理和超时管理 |
| Ros2TopicListener | 订阅ROS2 Topic获取实时状态（位置、电量、节点状态等） |
| Ros2LogCollector | 订阅 /rosout Topic采集所有ROS2节点日志，推送到LogService |
| LogService | 聚合系统日志+ROS2日志，写入文件并通过 /ws/v1/logs 推送到前端 |
| StatusService | 聚合ROS2状态数据，状态变更时通过 /ws/v1/status 推送到调度系统 |
| Ros2Manager | 管理ROS2节点的启停，通过ROS2 lifecycle接口或进程管理 |
| ArmService | 手臂运控+示教，示教数据以JSON文件存储在本地 |
| Supervisor | systemd service管理进程，崩溃自动重启 |

### 4.3 日志系统

**WebSocket端点**: `/ws/v1/logs`（前端直连）

**日志帧格式**:
```json
{
  "type": "log",
  "source": "system | ros2",
  "level": "debug | info | warn | error",
  "node": "move_node | gripper_node | ... | backend",
  "message": "Navigation goal reached",
  "timestamp": 1715400000000
}
```

**日志源**:
1. 后端系统日志 — Python logging handler 直接推送到WS
2. ROS2节点日志 — Ros2LogCollector 订阅 /rosout Topic 采集

**前端日志面板**:
- 实时滚动显示（最新在底部）
- 按级别颜色区分（debug=灰, info=白, warn=黄, error=红）
- 过滤器：level筛选 / source筛选 / node筛选 / 关键字搜索
- 自动暂停：用户滚动查看时暂停自动滚动

**日志存储**:
- 按天轮转，保留30天
- 存储路径：/opt/furance_robot/logs/

### 4.4 异常上报

| 场景 | 处理 |
|------|------|
| ROS2 Service调用超时 | 上报error电文到调度系统 |
| ROS2节点异常退出 | 上报error + 尝试自动重启 |
| 硬件异常（ROS2返回） | 上报error电文 |
| WebSocket断连 | 自动重连（指数退避） |

**错误码规范**:
- 1xxx — 通讯类（ROS2超时、WS断连）
- 2xxx — 硬件类（移动失败、夹爪异常）
- 3xxx — 业务类（任务冲突、参数无效）

### 4.5 示教功能

- 保存当前关节角度并命名
- 查询预设位列表
- 执行指定预设位
- 删除预设位
- 数据存储：本地JSON文件（/opt/furance_robot/data/teach/）

### 4.6 部署

```
/opt/furance_robot/
├── bin/robot_control_server       # PyInstaller可执行文件
├── static/                        # Vite build前端静态文件
├── config/config.yaml             # 运行配置（端口、ROS2域等）
├── data/teach/                    # 示教数据
├── logs/                          # 日志目录
└── service/robot_control.service  # systemd配置

开机自启：systemd service，Restart=always, RestartSec=5s
```

---

## 5. 调度系统详细设计

### 5.1 内部架构

```
前端 (Vue 3 + Vite)
  机器人状态 | 指令下发 | 任务编排 | 制样机状态
      └──────────┴──────────┴──────────┘
                    HTTP API
                      │
后端 (FastAPI + SQLite)
  API层: /api/v1/robot/... | /api/v1/task/... | /api/v1/sampler/...
      │
  Service层:
    RobotProxyService  - 转发指令到控制系统
    StatusService      - 接收并存储机器人状态
    TaskEngine         - 任务编排与执行引擎
    SamplerService     - 制样机控制与状态管理
    L2Listener [预留]  - L2指令监听与任务触发
      │
  Client层:
    RobotHttpClient   - HTTP客户端(调度→控制系统)
    RobotWsClient     - WS客户端(接收机器人状态)
    SamplerWsClient   - WS客户端(调度→制样机)
    L2Client(抽象)    - [预留] L2系统通讯客户端
      │
  Supervisor: nssm Windows服务
```

### 5.2 组件职责

| 组件 | 职责 |
|------|------|
| RobotProxyService | 接收前端指令，转发HTTP到控制系统，不直接与ROS2交互 |
| StatusService | 通过WebSocket接收机器人状态，存入SQLite，供前端查询 |
| TaskEngine | 解析任务模板→按步骤调用RobotProxyService/SamplerService→记录执行状态 |
| SamplerService | 通过WebSocket与制样机通讯，下发控制指令，接收状态 |
| L2Listener [预留] | 循环监听L2指令，匹配任务模板，触发TaskEngine执行 |
| RobotWsClient | 连接控制系统WS，接收状态上报，断连自动重连 |
| SamplerWsClient | 连接制样机WS，双向电文通讯，断连自动重连 |
| L2Client(抽象) [预留] | L2系统通讯抽象层，具体协议待定 |

### 5.3 任务编排引擎

**固定模板式**，后续扩展可视化编排。

**任务模板结构**:
```json
{
  "task_id": "sample_delivery",
  "name": "取样送样流程",
  "steps": [
    {"order":1, "action":"robot.move",   "params":{"map_id":"map_001", "waypoint_id":"wp_sample", "speed":0.5}},
    {"order":2, "action":"robot.grab",    "params":{"target":"sample_position"}},
    {"order":3, "action":"robot.move",    "params":{"map_id":"map_001", "waypoint_id":"wp_sampler", "speed":0.5}},
    {"order":4, "action":"robot.place",   "params":{"target":"sampler_input"}},
    {"order":5, "action":"sampler.start", "params":{}},
    {"order":6, "action":"wait_sampler_complete", "params":{}}
  ]
}
```

**支持的动作类型**:
- `robot.move / robot.grab / robot.place / robot.home`
- `robot.gripper / robot.lift / robot.charge / robot.enable`
- `sampler.start / sampler.stop`
- `wait_sampler_complete` — 等待制样机完成
- `delay` — 延时等待

**执行策略**: 顺序执行，某步骤失败则终止任务并上报。每步执行结果记录到 task_step_logs。

### 5.4 L2指令监听（预留）

**抽象接口**:
```python
class L2ListenerBase(ABC):
    async def start()                              # 启动监听循环
    async def stop()                               # 停止监听
    async def on_command(cmd)                      # 收到指令回调

class L2ClientBase(ABC):
    async def connect()                            # 建立连接
    async def disconnect()                         # 断开连接
    async def listen() -> AsyncIterator[dict]      # 监听指令流
    async def send_response(request_id, result)    # 回传执行结果
```

**处理流程**: L2指令 → L2Listener解析 → 匹配task_template → TaskEngine执行 → 结果回传L2

**配置**:
```yaml
l2:
  enabled: false          # 是否启用
  adapter: "default"      # 适配器名称，待实现
```

### 5.5 数据模型 (SQLite)

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| robots | 机器人注册 | id, name, control_url, ws_url, status, last_heartbeat |
| task_templates | 任务模板 | id, name, steps_json, created_at, updated_at |
| task_executions | 任务执行记录 | id, task_template_id, robot_id, status, started_at, completed_at, error_msg |
| task_step_logs | 步骤执行日志 | id, execution_id, step_order, action, params, result, status, started_at, completed_at |
| sampler_status | 制样机状态快照 | id, status, progress, last_update |
| robot_status | 机器人状态快照 | robot_id, position_json, gripper_json, arm_json, battery, task_status, updated_at |
| l2_commands | L2指令记录[预留] | id, l2_request_id, task_template_id, task_execution_id, command_json, status, received_at, completed_at, response_json |

### 5.6 部署

```
C:\FuranceDispatch\
├── bin\dispatch_server.exe        # PyInstaller可执行文件
├── static\                        # Vite build前端静态文件
├── config\config.yaml             # 运行配置（端口、机器人地址等）
├── data\dispatch.db               # SQLite数据库
├── logs\                          # 日志目录
└── service\                       # nssm服务配置

开机自启：nssm注册Windows服务，崩溃自动重启
```

---

## 6. 通讯协议

### 6.1 HTTP接口 — 调度→控制系统

**导航相关**:
```
GET  /api/v1/maps                            # 获取地图列表
GET  /api/v1/maps/{map_id}/waypoints         # 获取导航点位列表
POST /api/v1/robot/{robot_id}/move           # 移动 {map_id, waypoint_id, speed}
```

**上肢控制**:
```
POST /api/v1/robot/{robot_id}/home           # 归零位
POST /api/v1/robot/{robot_id}/grab           # 抓取 {target: "string"}
POST /api/v1/robot/{robot_id}/place          # 放置 {target: "string"}
POST /api/v1/robot/{robot_id}/gripper        # 夹爪开闭 {arm: "left"|"right", action: "open"|"close", force?: float}
```

**升降/充电/使能**:
```
POST /api/v1/robot/{robot_id}/lift           # 升降 {direction: "up"|"down", height: float}
POST /api/v1/robot/{robot_id}/charge         # 充电 {action: "start"|"stop"}
POST /api/v1/robot/{robot_id}/enable         # 使能+清错 {enable: bool, clear_error: bool}
```

**手臂运控（仅控制系统）**:
```
POST /api/v1/robot/{robot_id}/arm/move
     {arm: "left"|"right", method: "movep"|"moveL"|"moveJ",
      joint_angles?: [j1..j7], position?: {x,y,z,roll,pitch,yaw}, coordinate: "base_link"}
```

**示教功能（仅控制系统）**:
```
POST   /api/v1/robot/{robot_id}/arm/teach/save   # 保存当前角度 {arm, name}
GET    /api/v1/robot/{robot_id}/arm/teach/list    # 获取预设位列表
POST   /api/v1/robot/{robot_id}/arm/teach/exec    # 执行预设位 {arm, name}
DELETE /api/v1/robot/{robot_id}/arm/teach/{name}  # 删除预设位
```

**ROS2节点管理**:
```
GET  /api/v1/ros2/nodes                       # 节点列表
POST /api/v1/ros2/nodes/{node}/start          # 启动节点
POST /api/v1/ros2/nodes/{node}/stop           # 停止节点
GET  /api/v1/ros2/nodes/{node}/status         # 节点状态
```

**统一响应格式**:
```json
{"code": 0, "message": "ok", "data": {...}}
```

### 6.2 WebSocket电文 — 控制→调度（状态上报）

**连接**: `ws://<control_ip>:<port>/ws/v1/status`

**帧格式**:
```json
{
  "type": "status | error | log",
  "robot_id": "robot_001",
  "timestamp": 1715400000000,
  "payload": {
    // type=status
    "position": {"x": 1.0, "y": 2.0, "theta": 0.5},
    "current_map": "map_001",
    "lift_height": 0.3,
    "gripper": {
      "left":  {"state": "open"|"closed", "force": 50.0},
      "right": {"state": "open"|"closed", "force": 50.0}
    },
    "battery": 85,
    "charging": false,
    "enabled": true,
    "error_code": 0,
    "task_status": "idle | running | error",
    "arm": {
      "left":  {"joint_angles": [0,0,0,0,0,0,0], "status": "idle"},
      "right": {"joint_angles": [0,0,0,0,0,0,0], "status": "moving"}
    },
    "ros2_nodes": {"move_node": "running", "gripper_node": "stopped"}

    // type=error
    "error_code": 1001,
    "error_msg": "Gripper timeout",
    "source": "gripper_node"

    // type=log (上报到调度)
    "level": "info | warn | error",
    "source": "move_node",
    "message": "Navigation goal reached"
  }
}
```

**推送策略**: 状态变更立即推送 + 心跳(30s)

### 6.3 ROS2 Service接口 — 控制系统→ROS2节点

| Service | Request | Response |
|---------|---------|----------|
| /GetMapList | {} | {maps: [{id, name}]} |
| /GetWaypointList | {map_id} | {waypoints: [{id, name, x, y, theta}]} |
| /MoveCommand | {map_id, waypoint_id, speed} | {success, message} |
| /HomeCommand | {} | {success, message} |
| /GrabCommand | {target: "string"} | {success, message} |
| /PlaceCommand | {target: "string"} | {success, message} |
| /GripperCommand | {arm: "left"\|"right", action: "open"\|"close", force?: float(默认0=系统默认)} | {success, message} |
| /LiftCommand | {direction: "up"\|"down", height} | {success, message} |
| /ChargeCommand | {action: "start"\|"stop"} | {success, message} |
| /EnableCommand | {enable, clear_error} | {success, message} |
| /ArmMoveCommand | {arm, method, joint_angles, position, coordinate} | {success, message} |
| /ArmTeachSave | {arm, name} | {success, message, joint_angles: [j1..j7]} |
| /ArmTeachExec | {arm, name} | {success, message} |

注：所有Service采用统一Request/Response模式，控制系统为Client，ROS2节点为Server。

### 6.4 制样机WebSocket电文 — 调度→制样机

**连接**: `ws://<sampler_ip>:<port>/`（制样机为服务端）

**调度→制样机**:
```json
{
  "type": "command",
  "command": "start | stop | query",
  "params": {},
  "request_id": "uuid"
}
```

**制样机→调度**:
```json
{
  "type": "response | status | error",
  "request_id": "uuid",
  "payload": {
    "status": "idle | running | error | completed",
    "progress": 0-100,
    "error_msg": ""
  }
}
```

---

## 7. 预备功能

### 7.1 夹爪ROS2模块开发

- 通讯基于EtherCAT
- 支持左/右夹爪独立控制
- 支持指定力矩
- 接口已在上文ROS2 Service中定义（/GripperCommand）

### 7.2 L2系统通讯对接

- 抽象层已设计（L2Listener + L2Client）
- 具体协议待L2系统确定后实现
- 配置项 `l2.enabled` 控制启用

### 7.3 可视化任务编排

- 当前为固定模板式
- 后续扩展为前端拖拽式可视化编排
- TaskEngine接口已预留动态步骤支持
