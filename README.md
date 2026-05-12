# Furance Robot — 轮式双臂机器人控制与调度系统

## 项目概述

本系统用于控制轮式双臂机器人完成制样流程，采用分层代理架构：

- **控制系统 (robot_control)** — 硬件代理层，部署在 Ubuntu 22.04 工控机上，直接与 ROS2 通信
- **调度系统 (dispatch)** — 业务逻辑层，部署在 Windows 10 控制柜上，负责任务编排和多设备协调
- **共享包 (shared)** — 两个子系统的公共数据模型和协议定义

```
┌─────────────┐  HTTP/WS   ┌──────────────┐  ROS2 Srv/Topic  ┌──────────┐
│  调度系统     │◄─────────►│  控制系统      │◄───────────────►│ 机器人硬件 │
│ (Win10 柜)   │           │ (Ubuntu 工控机) │                  │          │
└─────────────┘           └──────────────┘                  └──────────┘
       │                        │
   制样机 WS              前端 Vue 页面
```

## 目录结构

```
furance_robot/
├── shared/                          # furance-shared Python 包
│   └── src/furance_shared/
│       ├── models/                  # 数据模型 (RobotStatus, Command, ...)
│       ├── protocol/                # 协议定义 (HTTP响应, WS帧格式)
│       └── utils/                   # 错误码, 枚举, 日志
├── robot_control/                   # 控制系统
│   ├── backend/app/
│   │   ├── api/                     # HTTP API 端点
│   │   ├── ros2/                    # ROS2 集成层 (Service/Topic/Log)
│   │   ├── services/                # 业务逻辑
│   │   ├── ws/                      # WebSocket 端点
│   │   ├── core/                    # 配置, 日志
│   │   └── models/                  # 本地数据模型
│   ├── frontend/src/                # Vue 3 前端
│   └── deploy/                      # 构建 & 部署脚本
├── dispatch/                        # 调度系统
│   ├── backend/app/
│   │   ├── api/                     # HTTP API 端点
│   │   ├── clients/                 # WS客户端 (控制/制样机/L2)
│   │   ├── services/                # 业务逻辑, 任务引擎
│   │   ├── core/                    # 配置, 数据库
│   │   └── models/                  # 数据模型
│   ├── frontend/src/                # Vue 3 前端
│   └── deploy/                      # 构建 & 部署脚本
└── docs/                            # 设计文档
```

## 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | >= 3.10 | 后端运行时 |
| Node.js | >= 18 | 前端构建 |
| ROS2 | Humble/Iron | 控制系统 Real 模式 (可选) |
| npm | >= 9 | 前端包管理 |
| pip | >= 23 | Python 包管理 |
| PyInstaller | >= 6.0 | 生产打包 |

---

## 快速开始

### 一键启动 (推荐)

```bash
./scripts/dev.sh
```

启动全部 4 个开发服务，自动安装依赖：

| 服务 | 端口 | 地址 |
|------|------|------|
| 控制系统后端 | 8000 | http://localhost:8000 |
| 控制系统前端 | 3000 | http://localhost:3000 |
| 调度系统后端 | 8001 | http://localhost:8001 |
| 调度系统前端 | 3001 | http://localhost:3001 |

```bash
./scripts/dev.sh          # 启动全部服务
./scripts/dev.sh stop     # 停止全部服务
./scripts/dev.sh restart  # 重启
./scripts/dev.sh status   # 查看运行状态
```

日志文件位于 `.dev_logs/` 目录，启动后会自动跟踪后端日志输出。

### 手动启动 (单独调试)

<details>
<summary>展开查看各服务单独启动命令</summary>

```bash
# 1. 安装共享包 (首次)
cd shared && pip install -e .

# 2. 控制系统后端
cd robot_control/backend
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 控制系统前端 (另开终端)
cd robot_control/frontend
npm install
npm run dev  # http://localhost:3000

# 4. 调度系统后端
cd dispatch/backend
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# 5. 调度系统前端 (另开终端)
cd dispatch/frontend
npm install
npm run dev  # http://localhost:3001
```

</details>

### 运行测试

```bash
# 单个子系统
cd shared && pytest tests/ -v                           # 35 tests
cd robot_control/backend && pytest tests/ -v            # 26 tests
cd dispatch/backend && pytest tests/ -v                 # 18 tests

# 全量测试
cd shared && pytest tests/ -v && \
cd ../robot_control/backend && pytest tests/ -v && \
cd ../../dispatch/backend && pytest tests/ -v
```

### 前端构建

```bash
cd robot_control/frontend && npm run build   # 产出 → dist/
cd dispatch/frontend && npm run build         # 产出 → dist/
```

---

## API 总览

### 控制系统 API (端口 8000)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/robot/{id}/home` | 归零 |
| POST | `/api/v1/robot/{id}/grab` | 抓取 |
| POST | `/api/v1/robot/{id}/place` | 放置 |
| POST | `/api/v1/robot/{id}/gripper` | 夹爪控制 |
| POST | `/api/v1/robot/{id}/lift` | 升降控制 |
| POST | `/api/v1/robot/{id}/charge` | 充电控制 |
| POST | `/api/v1/robot/{id}/enable` | 使能/清错 |
| POST | `/api/v1/robot/{id}/arm/move` | 手臂运动 |
| POST | `/api/v1/robot/{id}/arm/teach/save` | 保存示教 |
| GET  | `/api/v1/robot/{id}/arm/teach/list` | 示教列表 |
| POST | `/api/v1/robot/{id}/arm/teach/exec` | 执行示教 |
| DELETE | `/api/v1/robot/{id}/arm/teach/{name}` | 删除示教 |
| GET  | `/api/v1/maps` | 地图列表 |
| GET  | `/api/v1/maps/{id}/waypoints` | 导航点列表 |
| POST | `/api/v1/robot/{id}/move` | 导航移动 |
| GET  | `/api/v1/ros2/nodes` | ROS2 节点列表 |
| POST | `/api/v1/ros2/nodes/{name}/start` | 启动节点 |
| POST | `/api/v1/ros2/nodes/{name}/stop` | 停止节点 |
| GET  | `/api/v1/ros2/nodes/{name}/status` | 节点状态 |
| WS   | `/ws/v1/status` | 实时状态推送 |
| WS   | `/ws/v1/logs` | 实时日志推送 |

### 调度系统 API (端口 8001)

| 方法 | 路径 | 说明 |
|------|------|------|
| **机器人管理** | | |
| GET | `/api/v1/dispatch/robots` | 机器人列表 (含状态) |
| POST | `/api/v1/dispatch/robots` | 注册机器人 |
| DELETE | `/api/v1/dispatch/robots/{id}` | 删除机器人 |
| **机器人指令** | | |
| POST | `/api/v1/dispatch/robot/{id}/home` | 归零 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/grab` | 抓取 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/place` | 放置 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/gripper` | 夹爪控制 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/lift` | 升降控制 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/charge` | 充电控制 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/enable` | 使能控制 (代理) |
| POST | `/api/v1/dispatch/robot/{id}/move` | 导航移动 (代理) |
| GET | `/api/v1/dispatch/robot/{id}/status` | 机器人状态 (实时→DB→Mock) |
| **导航** | | |
| GET | `/api/v1/dispatch/maps` | 地图列表 (代理) |
| GET | `/api/v1/dispatch/maps/{id}/waypoints` | 导航点 (代理) |
| **任务模板** | | |
| GET | `/api/v1/dispatch/tasks/templates` | 模板列表 |
| GET | `/api/v1/dispatch/tasks/templates/{id}` | 模板详情 |
| POST | `/api/v1/dispatch/tasks/templates` | 创建模板 |
| PUT | `/api/v1/dispatch/tasks/templates/{id}` | 更新模板 |
| DELETE | `/api/v1/dispatch/tasks/templates/{id}` | 删除模板 |
| **任务执行** | | |
| POST | `/api/v1/dispatch/tasks/execute` | 执行任务 |
| GET | `/api/v1/dispatch/tasks/executions` | 执行记录列表 |
| GET | `/api/v1/dispatch/tasks/executions/{id}` | 执行详情 (含步骤) |
| POST | `/api/v1/dispatch/tasks/executions/{id}/cancel` | 取消执行 |
| **制样机** | | |
| POST | `/api/v1/dispatch/sampler/command` | 制样机指令 (start/stop/query) |
| GET | `/api/v1/dispatch/sampler/status` | 制样机状态 (实时→DB→Mock) |

### 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

### WebSocket 帧格式

```json
// 状态帧
{"type": "status", "robot_id": "robot_001", "timestamp": 1715400000000, "payload": {"position": {...}, "battery": 80, ...}}

// 日志帧
{"type": "log", "robot_id": "robot_001", "timestamp": 1715400000000, "payload": {"source": "ros2", "level": "info", "node": "move_node", "message": "..."}}

// 错误帧
{"type": "error", "robot_id": "robot_001", "timestamp": 1715400000000, "payload": {"error_code": 2001, "error_msg": "...", "source": "arm"}}
```

---

## 调度系统数据库

调度系统使用 SQLite 持久化存储，路径由 `DATABASE_PATH` 环境变量或 `config.yaml` 的 `database.path` 字段控制。首次启动时自动建表并写入种子数据（3个任务模板 + 配置中的机器人）。

### 数据表设计

#### robots — 机器人注册表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PRIMARY KEY | 机器人唯一标识 |
| name | TEXT | NOT NULL | 机器人名称 |
| control_url | TEXT | NOT NULL | 控制系统 HTTP 地址 |
| ws_url | TEXT | NOT NULL | 控制系统 WebSocket 地址 |
| status | TEXT | DEFAULT 'offline' | 在线状态 |
| last_heartbeat | REAL | DEFAULT 0 | 最后心跳时间戳 |

#### robot_status — 机器人实时状态 (缓存)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| robot_id | TEXT | PRIMARY KEY → robots.id | 机器人ID |
| position_json | TEXT | DEFAULT '{}' | 位置信息 JSON |
| gripper_json | TEXT | DEFAULT '{}' | 夹爪状态 JSON |
| arm_json | TEXT | DEFAULT '{}' | 手臂状态 JSON |
| battery | INTEGER | DEFAULT 0 | 电量百分比 |
| charging | INTEGER | DEFAULT 0 | 充电状态 (0/1) |
| enabled | INTEGER | DEFAULT 0 | 使能状态 (0/1) |
| error_code | INTEGER | DEFAULT 0 | 错误码 |
| task_status | TEXT | DEFAULT 'idle' | 任务状态 |
| updated_at | REAL | DEFAULT 0 | 更新时间戳 |

状态读取策略：实时数据 → DB 缓存 → Mock 数据。

#### task_templates — 任务模板

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | TEXT | PRIMARY KEY | 模板唯一标识 |
| name | TEXT | NOT NULL | 模板名称 |
| steps_json | TEXT | NOT NULL | 步骤定义 JSON |
| created_at | REAL | NOT NULL | 创建时间戳 |
| updated_at | REAL | NOT NULL | 更新时间戳 |

`steps_json` 格式：

```json
{
  "steps": [
    {"order": 1, "action": "robot.home", "params": {}},
    {"order": 2, "action": "robot.move", "params": {"map_id": "workshop_map", "waypoint_id": "wp_02"}},
    {"order": 3, "action": "sampler.start", "params": {}}
  ]
}
```

支持的 action 前缀：
- `robot.*` — 代理到控制系统 (home, move, grab, place, gripper, lift, charge, enable)
- `sampler.*` — 调用制样机服务 (start, stop)
- `wait_sampler_complete` — 等待制样完成
- `delay` — 延时等待，参数 `seconds`

#### task_executions — 任务执行记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 执行ID |
| task_template_id | TEXT | NOT NULL → task_templates.id | 关联模板 |
| robot_id | TEXT | NOT NULL | 执行机器人 |
| status | TEXT | DEFAULT 'pending' | 状态: pending/running/completed/failed/cancelled |
| started_at | REAL | | 开始时间戳 |
| completed_at | REAL | | 完成时间戳 |
| error_msg | TEXT | | 失败原因 |

#### task_step_logs — 任务步骤日志

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 日志ID |
| execution_id | INTEGER | NOT NULL → task_executions.id | 关联执行 |
| step_order | INTEGER | NOT NULL | 步骤序号 |
| action | TEXT | NOT NULL | 动作名称 |
| params_json | TEXT | | 参数 JSON |
| result_json | TEXT | | 执行结果 JSON |
| status | TEXT | DEFAULT 'pending' | 状态: pending/completed/failed |
| started_at | REAL | | 开始时间戳 |
| completed_at | REAL | | 完成时间戳 |

#### sampler_status — 制样机状态 (缓存)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 记录ID |
| status | TEXT | DEFAULT 'idle' | 状态: idle/running/completed/error |
| progress | INTEGER | DEFAULT 0 | 进度百分比 |
| last_update | REAL | NOT NULL | 更新时间戳 |

#### l2_commands — L2 接口命令 (预留)

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY AUTOINCREMENT | 命令ID |
| l2_request_id | TEXT | | L2 请求ID |
| task_template_id | TEXT | | 关联模板 |
| task_execution_id | INTEGER | | 关联执行 |
| command_json | TEXT | | 命令内容 JSON |
| status | TEXT | DEFAULT 'pending' | 状态 |
| received_at | REAL | | 接收时间戳 |
| completed_at | REAL | | 完成时间戳 |
| response_json | TEXT | | 响应内容 JSON |

### 种子数据

首次启动时自动插入：

- **3个任务模板**: `auto_sample` (自动制样流程), `charge_and_wait` (充电等待), `grab_place_cycle` (抓放循环)
- **机器人**: 从 `config.yaml` 的 `robots` 配置中读取

### ER 关系

```
robots ──1:1── robot_status
  │
  └──1:N── task_executions ──1:N── task_step_logs
                │
task_templates ──1:N──┘
                │
            l2_commands ──N:1──┘
```

---

## ROS2 集成

### 模式切换

通过环境变量 `ROS2_MODE` 控制：

| 模式 | 环境变量 | 说明 |
|------|---------|------|
| Mock | `ROS2_MODE=mock` (默认) | 不需要 ROS2 环境，返回固定响应 |
| Real | `ROS2_MODE=real` | 连接真实 ROS2 节点，需要 ROS2 环境 |

```bash
# Mock 模式 (开发/测试)
uvicorn app.main:app --port 8000

# Real 模式 (生产部署)
export ROS2_MODE=real
uvicorn app.main:app --port 8000
```

### ROS2 Service 接口

所有机器人指令通过统一的 `furance_interfaces/srv/GenericCommand` 接口调用：

```
# Request
string command        # 指令名: "home", "grab", "place", "gripper", "lift", ...
string params_json    # JSON 编码的参数

---
# Response
bool success
string message
string result_json    # JSON 编码的结果
```

对应 ROS2 Service 名称：

| Service 名 | 指令 |
|------------|------|
| `/HomeCommand` | 归零 |
| `/GrabCommand` | 抓取 |
| `/PlaceCommand` | 放置 |
| `/GripperCommand` | 夹爪 |
| `/LiftCommand` | 升降 |
| `/ChargeCommand` | 充电 |
| `/EnableCommand` | 使能 |
| `/ArmMoveCommand` | 手臂运动 |
| `/ArmTeachExec` | 示教执行 |
| `/MoveCommand` | 导航移动 |
| `/GetMapList` | 地图列表 |
| `/GetWaypointList` | 导航点列表 |
| `/GetNodeList` | 节点列表 |
| `/NodeStart` | 启动节点 |
| `/NodeStop` | 停止节点 |
| `/NodeStatus` | 节点状态 |

### ROS2 Topic 订阅

| Topic | 类型 | 说明 |
|-------|------|------|
| `/robot_status` | `std_msgs/String` | 机器人状态 (JSON 编码) |
| `/rosout` | `rcl_interfaces/msg/Log` | ROS2 日志 |

### 构建 furance_interfaces 包

Real 模式需要先构建自定义 ROS2 接口包：

```bash
# 在 ROS2 工作空间中
mkdir -p ros2_ws/src
# 将 furance_interfaces 包放入 ros2_ws/src/
cd ros2_ws
colcon build --packages-select furance_interfaces
source install/setup.bash
```

---

## 生产部署

### 控制系统 — Ubuntu 22.04 工控机

#### 构建

```bash
cd robot_control/deploy
chmod +x build.sh
./build.sh
# 产出: robot_control/deploy/dist/robot_control/
```

构建脚本执行流程：
1. 安装 `furance-shared` 到本地
2. 安装后端 Python 依赖 + PyInstaller
3. `npm install && npm run build` 构建前端
4. PyInstaller 打包为可执行文件

#### 安装

```bash
cd robot_control/deploy
sudo ./install.sh
```

安装流程：
1. 创建 `/opt/furance_robot/{bin,static,config,data/teach,logs}` 目录
2. 复制可执行文件、前端静态文件、配置文件
3. 安装 systemd 服务
4. 启用开机自启并启动服务

#### 服务管理

```bash
# 查看状态
systemctl status robot_control

# 查看日志
journalctl -u robot_control -f

# 重启
systemctl restart robot_control

# 停止
systemctl stop robot_control
```

#### 卸载

```bash
cd robot_control/deploy
sudo ./uninstall.sh
```

#### 目录布局

```
/opt/furance_robot/
├── bin/robot_control_server    # 可执行文件
├── static/                     # 前端静态文件
├── config/config.yaml          # 配置文件
├── data/teach/                 # 示教数据
├── logs/                       # 日志文件
└── service/                    # 服务文件
```

### 调度系统 — Windows 10 控制柜

#### 构建

在 Windows 或 Linux (WSL) 上：

```bash
cd dispatch/deploy
chmod +x build.sh
./build.sh
# 产出: dispatch/deploy/dist/dispatch/
```

#### 安装

1. 将 `dispatch/deploy/dist/` 目录复制到 Windows 机器
2. 以管理员身份运行 `install.bat`

安装流程：
1. 创建 `C:\FuranceDispatch\{bin,static,config,data,logs}` 目录
2. 复制可执行文件和前端静态文件
3. 下载 nssm (Windows 服务管理器)
4. 注册 `FuranceDispatch` Windows 服务并启动

#### 服务管理

```cmd
:: 查看状态
sc query FuranceDispatch

:: 停止
net stop FuranceDispatch

:: 启动
net start FuranceDispatch
```

#### 卸载

以管理员身份运行 `uninstall.bat`

#### 目录布局

```
C:\FuranceDispatch\
├── bin\dispatch_server.exe     # 可执行文件
├── static\                     # 前端静态文件
├── config\config.yaml          # 配置文件
├── data\dispatch.db            # SQLite 数据库
├── logs\                       # 日志文件
└── service\nssm.exe            # 服务管理器
```

---

## 配置说明

### 控制系统 config.yaml

```yaml
server:
  host: "0.0.0.0"
  port: 8000

ros2:
  domain_id: 0              # ROS2 Domain ID
  service_timeout: 30.0     # Service 调用超时 (秒)

websocket:
  status_interval: 30       # 状态推送间隔 (秒)

logging:
  level: "INFO"
  dir: "/opt/furance_robot/logs"
  retention_days: 30

teach:
  data_dir: "/opt/furance_robot/data/teach"
```

### 调度系统 config.yaml

```yaml
server:
  host: "0.0.0.0"
  port: 8000

robots:
  - id: "robot_001"
    name: "1号机器人"
    control_url: "http://192.168.1.100:8000"        # 控制系统地址
    ws_url: "ws://192.168.1.100:8000/ws/v1/status"   # 状态WS地址

sampler:
  ws_url: "ws://192.168.1.200:9000"                  # 制样机WS地址

l2:
  enabled: false           # L2接口 (预留)
  adapter: "default"

database:
  path: "./data/dispatch.db"

logging:
  level: "INFO"
  dir: "C:\\FuranceDispatch\\logs"
  retention_days: 30
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ROS2_MODE` | `mock` | ROS2 模式: `mock` 或 `real` |
| `STATIC_DIR` | — | 前端静态文件目录 (生产部署) |
| `TEACH_DATA_DIR` | `/opt/furance_robot/data/teach` | 示教数据目录 |
| `LOG_DIR` | `/opt/furance_robot/logs` | 日志目录 |
| `DATABASE_PATH` | `./data/dispatch.db` | SQLite 数据库路径 (调度系统) |

---

## 调试指南

### Swagger API 文档

FastAPI 自动生成交互式 API 文档，可直接在浏览器中测试接口：

| 系统 | 地址 |
|------|------|
| 控制系统 Swagger | http://localhost:8000/docs |
| 控制系统 ReDoc | http://localhost:8000/redoc |
| 调度系统 Swagger | http://localhost:8001/docs |
| 调度系统 ReDoc | http://localhost:8001/redoc |

Swagger UI 支持直接发送请求并查看响应，无需 Postman。

### HTTP 接口调试

```bash
# 归零指令
curl -X POST http://localhost:8000/api/v1/robot/robot_001/home

# 抓取指令
curl -X POST http://localhost:8000/api/v1/robot/robot_001/grab \
  -H "Content-Type: application/json" \
  -d '{"target": "sample_pos"}'

# 夹爪控制
curl -X POST http://localhost:8000/api/v1/robot/robot_001/gripper \
  -H "Content-Type: application/json" \
  -d '{"arm": "left", "action": "close", "force": 50.0}'

# 手臂运动
curl -X POST http://localhost:8000/api/v1/robot/robot_001/arm/move \
  -H "Content-Type: application/json" \
  -d '{"arm": "left", "method": "moveJ", "joint_angles": [0,0,0,0,0,0,0], "coordinate": "base_link"}'

# 查询地图 (调度系统代理)
curl http://localhost:8001/api/v1/dispatch/maps

# 任务模板列表
curl http://localhost:8001/api/v1/dispatch/tasks/templates

# 创建任务模板
curl -X POST http://localhost:8001/api/v1/dispatch/tasks/templates \
  -H "Content-Type: application/json" \
  -d '{"id": "my_task", "name": "自定义流程", "steps": [{"order": 1, "action": "robot.home", "params": {}}]}'

# 执行任务
curl -X POST http://localhost:8001/api/v1/dispatch/tasks/execute \
  -H "Content-Type: application/json" \
  -d '{"template_id": "auto_sample", "robot_id": "robot_001"}'

# 注册机器人
curl -X POST http://localhost:8001/api/v1/dispatch/robots \
  -H "Content-Type: application/json" \
  -d '{"id": "robot_002", "name": "2号机器人", "control_url": "http://192.168.1.101:8000", "ws_url": "ws://192.168.1.101:8000/ws/v1/status"}'
```

### WebSocket 调试

使用浏览器开发者工具或命令行工具连接 WebSocket：

```bash
# 安装 wscat
npm install -g wscat

# 订阅机器人状态
wscat -c ws://localhost:8000/ws/v1/status

# 订阅运行日志
wscat -c ws://localhost:8000/ws/v1/logs

# 调度系统状态订阅 (连接控制系统的 WS)
wscat -c ws://192.168.1.100:8000/ws/v1/status
```

也可在浏览器控制台中调试：

```javascript
// 在 http://localhost:3000 页面控制台中执行
const ws = new WebSocket('ws://localhost:8000/ws/v1/status')
ws.onmessage = (e) => console.log(JSON.parse(e.data))
ws.onclose = () => console.log('disconnected')
```

### 后端热重载

开发模式下 uvicorn 启用时加 `--reload` 参数，修改 Python 代码后自动重启：

```bash
uvicorn app.main:app --port 8000 --reload
```

前端 Vite 开发服务器默认启用 HMR，修改 `.vue`/`.js` 文件后自动刷新。

### 日志级别调整

通过环境变量切换日志级别，无需修改代码：

```bash
# DEBUG 级别 — 输出所有请求/响应细节
LOG_LEVEL=DEBUG uvicorn app.main:app --port 8000 --reload

# 也可在 config.yaml 中设置
# logging:
#   level: "DEBUG"
```

### ROS2 调试

```bash
# 查看当前话题列表
ros2 topic list

# 实时查看机器人状态话题
ros2 topic echo /robot_status

# 查看 ROS2 日志
ros2 topic echo /rosout

# 手动调用 Service 测试
ros2 service call /HomeCommand furance_interfaces/srv/GenericCommand \
  "{command: 'home', params_json: '{}'}"

ros2 service call /GrabCommand furance_interfaces/srv/GenericCommand \
  "{command: 'grab', params_json: '{\"target\": \"sample_pos\"}'}"

# 发布模拟状态数据 (测试前端推送)
ros2 topic pub /robot_status std_msgs/String \
  '{data: "{\"position\":{\"x\":1.0,\"y\":2.0,\"theta\":0.5},\"battery\":85,\"charging\":false}"}' \
  --once

# 查看 Service 列表和类型
ros2 service list
ros2 service type /HomeCommand
```

### 常用调试场景

| 场景 | 操作 |
|------|------|
| 接口返回 422 | 查看 Swagger 文档确认请求体格式，或检查 Pydantic 校验错误详情 |
| WebSocket 无数据 | 确认后端日志有 WS 连接记录；Mock 模式不会主动推送数据 |
| 前端请求 404 | 确认 Vite proxy 配置指向正确的后端端口 |
| ROS2 Service 超时 | 确认 `ROS2_MODE=real`，检查 ROS2 节点是否运行: `ros2 node list` |
| 示教数据丢失 | 检查 `TEACH_DATA_DIR` 目录是否存在且有写权限 |
| 调度数据库错误 | 检查 `DATABASE_PATH` 目录是否存在: `mkdir -p data` |

---

## 开发规范

### Git 提交

格式: `<type>: <message>`

type 取值: `feat` / `fix` / `chore` / `docs` / `refactor` / `test`

### Python 代码

- Python 3.10+，使用 type hints
- Linter: `ruff` (配置见 `ruff.toml`)
- 测试: `pytest` + `pytest-asyncio`
- 数据模型: Pydantic v2
- 异步: `async/await`，禁止同步阻塞调用

### 前端代码

- Vue 3 + Vite + Element Plus
- 功能性优先，工业风格

### 通讯协议

- HTTP: RESTful，统一响应 `{code, message, data}`
- WebSocket: JSON 帧，`type` 字段区分 (`status`/`error`/`log`)
- ROS2: Service 模式 (Request/Response)
- 错误码: `1xxx` 通讯类, `2xxx` 硬件类, `3xxx` 业务类

---

## 前端页面说明

### 控制系统前端 (http://localhost:3000)

| 页面 | 路径 | 功能 |
|------|------|------|
| 状态监控 | `/` | 位置、电量、夹爪、手臂、任务状态总览 |
| 指令面板 | `/commands` | 归零、抓取、放置、夹爪、升降、充电、使能 |
| 手臂运控 | `/arm` | 手臂运动 + 示教管理 |
| 导航 | `/navigation` | 地图选择、导航点移动 |
| ROS2节点 | `/ros2` | 节点列表、启停控制 |
| 运行日志 | `/logs` | 实时日志流，按级别过滤 |

### 调度系统前端 (http://localhost:3001)

| 页面 | 路径 | 功能 |
|------|------|------|
| 总览 | `/` | 机器人 + 制样机状态卡片 |
| 机器人控制 | `/robot` | 指令下发 (代理) |
| 任务管理 | `/tasks` | 模板管理 + 执行 + 历史记录 |
| 制样机 | `/sampler` | 制样机状态 + 控制 |

---

## 常见问题

### Q: 启动后端报 `address already in use`

```bash
# 检查端口占用
ss -tlnp sport = :8000
# 或
fuser 8000/tcp

# 终止占用进程
fuser -k 8000/tcp

# 常见原因: Docker 容器占用了端口
docker ps  # 检查是否有容器映射了 8000 端口
docker stop <container_name>  # 停止占用端口的容器
```

使用 `./scripts/dev.sh stop` 可清理脚本启动的残留进程，但无法清理 Docker 容器或其他外部进程。

### Q: ROS2 Real 模式启动失败

1. 确认 ROS2 环境已 source: `source /opt/ros/humble/setup.bash`
2. 确认 `furance_interfaces` 包已构建并 source
3. 如无 ROS2 环境，使用默认 Mock 模式

### Q: 调度系统启动报数据库路径错误

```bash
mkdir -p dispatch/backend/data
# 或: export DATABASE_PATH=/tmp/dispatch.db
```

### Q: 前端 `npm install` 失败

确认 Node.js >= 18：`node --version`

### Q: 测试中示教测试报 Permission denied

默认 `teach_data_dir` 为 `/opt/furance_robot/data/teach`，测试会自动使用临时目录。手动运行时设置 `TEACH_DATA_DIR=/tmp/teach`。
