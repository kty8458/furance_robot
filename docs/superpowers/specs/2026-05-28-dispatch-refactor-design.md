# 调度系统重构设计

## 概述

基于现有控制系统功能重构调度系统。调度系统作为中央协调者，负责任务编排、workflow调度执行、状态监控、报警管理和日志记录。调度系统不再直接向机器人底盘发送导航指令，底盘导航通过控制系统的workflow间接调用。

## 架构

```
                    ┌─────────────┐
                    │   L2系统     │ (预留)
                    └──────┬──────┘
                           │ HTTP/WS (预留)
                           ▼
    ┌──────────────────────────────────────────────┐
    │              调度系统 (Win10)                  │
    │                                              │
    │  ┌──────────┐ ┌──────────┐ ┌─────────────┐  │
    │  │ 任务编排  │ │ 任务执行  │ │  状态监控    │  │
    │  │ 模块      │ │ 引擎      │ │  模块       │  │
    │  └──────────┘ └────┬─────┘ └──────┬──────┘  │
    │                    │               │         │
    │  ┌──────────┐     │               │         │
    │  │ 报警模块  │     │               │         │
    │  └──────────┘     │               │         │
    │                    ▼               ▼         │
    │            HTTP ───────────────── WS         │
    └───────┬──────────────────────────────────────┘
            │                          │
    ┌───────▼──────────┐     ┌────────▼──────────┐
    │ 控制系统(Ubuntu)  │     │ 制样机             │
    │ (工控机)          │     │ (独立设备)         │
    │                  │     │                   │
    │ HTTP API         │     │ 通信方式待定       │
    │ WebSocket推送     │     │ (当前用模拟器代替) │
    │ ROS2集成          │     │                   │
    └──────────────────┘     └───────────────────┘

模拟控制系统 (独立进程)          模拟制样机 (独立进程)
├── HTTP API (完全模拟)          ├── HTTP/WS API
├── WebSocket推送                 ├── 可配置异常概率和延迟
├── 可配置异常概率和延迟            └── 无ROS2依赖
└── 无ROS2依赖
```

### 关键约束
- 控制系统和制样机不能直接通信，调度系统是唯一协调者
- 控制系统的代码只能添加，不能删除重构
- 调度系统的代码可以做删除重构
- 控制系统和调度系统部署在不同设备上

---

## 一、控制系统新增功能 (robot_control/)

控制系统的代码只能做添加补充，不能删除。

### 1.1 Workflow异步执行 + step进度推送

当前 `execute_workflow` 是同步的，改为异步：HTTP立即返回execution_id，通过WebSocket推送step进度。

#### HTTP API 变更

| 接口 | 变更类型 | 说明 |
|------|---------|------|
| `POST /api/v1/robot/{robot_id}/workflows/{name}/execute` | 修改 | 改为异步，立即返回 `{execution_id, status: "started"}`，后台执行 |
| `POST /api/v1/robot/{robot_id}/workflows/{name}/cancel` | 新增 | 取消正在执行的workflow |
| `GET /api/v1/robot/{robot_id}/workflows/executions/{execution_id}` | 新增 | 查询某次执行的状态 |

#### 新增 WS 帧类型: `workflow_step`

```python
class WorkflowStepPayload(BaseModel):
    workflow_name: str
    execution_id: str
    step_id: str
    step_index: int          # 1-based
    total_steps: int
    status: Literal["running", "completed", "failed", "cancelled"]
    message: str = ""
    data: dict = {}

class WorkflowStepFrame(BaseModel):
    type: WsFrameType = "workflow_step"
    robot_id: str
    timestamp: Optional[int] = None
    payload: WorkflowStepPayload
```

推送时机：每个step开始前推送 `running`，完成后推送 `completed`/`failed`/`cancelled`。

#### 新增 WS 帧类型: `alarm`

```python
class AlarmPayload(BaseModel):
    alarm_id: str
    level: Literal["warning", "critical"]
    category: str            # arm/chassis/gripper/battery/system/...
    title: str
    message: str
    source: str

class AlarmFrame(BaseModel):
    type: WsFrameType = "alarm"
    robot_id: str
    timestamp: Optional[int] = None
    payload: AlarmPayload
```

### 1.2 Workflow取消流程

`POST /api/v1/robot/{robot_id}/workflows/{name}/cancel` 后台执行：

1. 设置workflow取消标志位 → 后续step不再执行
2. 如果当前正在执行move step → 调用底盘 `stop_task()` 停止导航
3. 如果当前正在执行arm step → 调用 `enable(False)` 下使能 + `clear_error()` 清错
4. 推送 `workflow_step` 帧（status=cancelled）

#### WorkflowService 内部改动

```python
class WorkflowService:
    def __init__(self, ...):
        self._active_executions: dict[str, asyncio.Event] = {}  # execution_id -> cancel_event

    async def execute_workflow(self, robot_id, name, execute_req):
        execution_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event
        try:
            for step in workflow.steps:
                if cancel_event.is_set():
                    await self._push_step_frame(..., status="cancelled")
                    break
                await self._push_step_frame(..., status="running")
                result = await self._dispatch_step(step, ...)
                await self._push_step_frame(..., status="completed" if result.success else "failed")
        finally:
            self._active_executions.pop(execution_id, None)

    async def cancel_workflow(self, robot_id, name):
        # 找到该workflow的活跃执行
        for exec_id, event in self._active_executions.items():
            event.set()
        # 停止底盘导航
        await self._chassis.stop_task()
        # 停止上肢
        await self._arm_enable_client.enable(False)
        await self._arm_enable_client.clear_error()
```

#### 新增 WS 路由: workflow_step

新建 `robot_control/backend/app/ws/workflow.py`，复用StatusService的广播机制或新建WorkflowProgressService来推送workflow_step帧。

### 1.3 状态推送确认

当前 `StatusPayload` 已包含所需字段：
- `position` — 底盘位置
- `gripper` — 夹爪状态
- `arm` — 手臂关节角和状态
- `battery` — 电量
- `charging` — 充电状态
- `enabled` — 使能状态
- `error_code` — 错误码
- `task_status` — 任务状态

无需新增字段。

---

## 二、调度系统重构 (dispatch/)

### 2.1 目录结构

```
dispatch/backend/app/
├── main.py                    # 重构：更新路由注册
├── api/
│   ├── __init__.py
│   ├── robots.py              # 新建：机器人列表+状态查询
│   ├── tasks.py               # 重构：任务编排CRUD
│   ├── executions.py          # 新建：任务执行触发+历史+取消
│   ├── alarms.py              # 新建：报警列表+确认+规则配置
│   ├── logs.py                # 新建：运行日志查询
│   └── sampler.py             # 保留重构：制样机控制
├── services/
│   ├── __init__.py
│   ├── task_editor.py         # 新建：任务模板CRUD服务
│   ├── task_executor.py       # 新建：任务执行引擎
│   ├── robot_proxy.py         # 保留重构：机器人HTTP代理
│   ├── status_monitor.py      # 新建：WS状态监控+轮询fallback
│   ├── alarm_service.py       # 新建：报警管理+规则引擎
│   ├── log_service.py         # 新建：日志存储+查询
│   ├── sampler_service.py     # 保留重构：制样机通信
│   └── l2_listener.py         # 保留：L2监听（预留）
├── clients/
│   ├── __init__.py
│   ├── robot_http.py          # 保留
│   ├── robot_ws.py            # 新建：机器人WS客户端
│   ├── sampler_ws.py          # 保留重构
│   └── l2_client.py           # 保留
├── core/
│   ├── __init__.py
│   ├── config.py              # 重构：更新配置项
│   └── database.py            # 重构：更新schema
└── models/
    ├── __init__.py
    ├── task.py                # 新建：任务模板+执行模型
    └── alarm.py               # 新建：报警模型
```

### 2.2 数据库 Schema

```sql
-- 机器人注册表
CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    control_url TEXT NOT NULL,
    ws_url TEXT NOT NULL,
    status TEXT DEFAULT 'offline',
    last_heartbeat REAL DEFAULT 0
);

-- 任务模板
CREATE TABLE IF NOT EXISTS task_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    steps_json TEXT NOT NULL,    -- list[TaskStep]
    version INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

-- 任务执行记录
CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_template_id TEXT NOT NULL,
    trigger_type TEXT DEFAULT 'manual',  -- manual / l2
    status TEXT DEFAULT 'pending',       -- pending / running / completed / failed / cancelled
    started_at REAL,
    completed_at REAL,
    error_msg TEXT,
    current_step_id TEXT
);

-- 执行步骤日志（每个task step对应一个workflow执行或sampler指令）
CREATE TABLE IF NOT EXISTS execution_step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    step_type TEXT NOT NULL,       -- workflow / sampler / delay
    step_config_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending / running / completed / failed / cancelled
    sub_step_results_json TEXT,    -- 来自控制系统的workflow_step帧汇总
    started_at REAL,
    completed_at REAL,
    error_msg TEXT
);

-- 报警记录
CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    robot_id TEXT DEFAULT '',
    source TEXT DEFAULT '',          -- robot / sampler / dispatch
    level TEXT NOT NULL,             -- warning / critical
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    ack_status TEXT DEFAULT 'unack', -- unack / acked
    ack_by TEXT DEFAULT '',
    ack_at REAL,
    created_at REAL NOT NULL
);

-- 报警规则配置
CREATE TABLE IF NOT EXISTS alarm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,             -- warning / critical
    condition_json TEXT NOT NULL,    -- 触发条件
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);

-- 运行日志
CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,            -- robot_control / dispatch / sampler
    robot_id TEXT DEFAULT '',
    level TEXT NOT NULL,             -- info / warn / error
    node TEXT DEFAULT '',
    message TEXT NOT NULL,
    created_at REAL NOT NULL
);

-- 机器人状态快照
CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    status_json TEXT DEFAULT '{}',
    updated_at REAL DEFAULT 0
);

-- 制样机状态
CREATE TABLE IF NOT EXISTS sampler_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'idle',
    progress INTEGER DEFAULT 0,
    status_json TEXT DEFAULT '{}',
    last_update REAL NOT NULL
);
```

删除旧表：`task_step_logs`（被 `execution_step_logs` 替代）。

### 2.3 数据模型

```python
# dispatch/backend/app/models/task.py

class TaskStepType(StrEnum):
    WORKFLOW = "workflow"
    SAMPLER = "sampler"
    DELAY = "delay"

class WorkflowStepConfig(BaseModel):
    robot_id: str
    workflow_name: str
    nav_params: list[NavPointParam] = []

class SamplerStepConfig(BaseModel):
    command: str
    params: dict = {}

class DelayStepConfig(BaseModel):
    seconds: float = Field(gt=0, default=1.0)

class TaskStep(BaseModel):
    id: str
    type: TaskStepType
    label: str = ""
    config: dict = {}  # WorkflowStepConfig | SamplerStepConfig | DelayStepConfig

class TaskTemplate(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: list[TaskStep] = []
    version: int = 1

# dispatch/backend/app/models/alarm.py

class AlarmLevel(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"

class AlarmSource(StrEnum):
    ROBOT = "robot"
    SAMPLER = "sampler"
    DISPATCH = "dispatch"

class AlarmAckStatus(StrEnum):
    UNACK = "unack"
    ACKED = "acked"
```

### 2.4 API 设计

#### 机器人状态
```
GET  /api/v1/dispatch/robots                    # 机器人列表+在线状态+最新数据
GET  /api/v1/dispatch/robots/{id}/status         # 单个机器人详细状态
POST /api/v1/dispatch/robots                     # 注册机器人
DELETE /api/v1/dispatch/robots/{id}              # 删除机器人
```

#### 任务编排
```
GET    /api/v1/dispatch/tasks                    # 任务模板列表
POST   /api/v1/dispatch/tasks                    # 创建任务模板
GET    /api/v1/dispatch/tasks/{id}               # 任务模板详情
PUT    /api/v1/dispatch/tasks/{id}               # 更新任务模板
DELETE /api/v1/dispatch/tasks/{id}               # 删除任务模板
```

#### 任务执行
```
POST /api/v1/dispatch/tasks/{id}/execute          # 手动触发执行
POST /api/v1/dispatch/tasks/{id}/execute/l2       # L2触发执行（预留）
GET  /api/v1/dispatch/executions                  # 执行历史列表
GET  /api/v1/dispatch/executions/{id}             # 执行详情（含步骤状态）
POST /api/v1/dispatch/executions/{id}/cancel      # 取消执行
POST /api/v1/dispatch/executions/{id}/pause       # 暂停执行
POST /api/v1/dispatch/executions/{id}/resume      # 恢复执行
```

#### 报警
```
GET  /api/v1/dispatch/alarms                      # 报警列表（支持 level/time/robot_id/ack_status 筛选）
POST /api/v1/dispatch/alarms/{id}/ack             # 确认报警
GET  /api/v1/dispatch/alarms/rules                # 报警规则列表
POST /api/v1/dispatch/alarms/rules                # 创建规则
PUT  /api/v1/dispatch/alarms/rules/{id}           # 更新规则
DELETE /api/v1/dispatch/alarms/rules/{id}         # 删除规则
```

#### 运行日志
```
GET /api/v1/dispatch/logs                         # 日志列表（支持 level/time/robot_id/source 筛选）
```

#### 制样机
```
POST /api/v1/dispatch/sampler/command             # 下发指令
GET  /api/v1/dispatch/sampler/status              # 查询状态
```

### 2.5 任务执行引擎流程

```
用户/L2触发 → TaskExecutor.execute(task_template_id)
  │
  ├─ 1. 创建 task_execution 记录 (status=running)
  │
  ├─ 2. 按序遍历 task_template.steps:
  │   ├─ type=workflow:
  │   │   ├─ HTTP POST → 控制系统 /workflows/{name}/execute
  │   │   ├─ 接收 WS workflow_step 帧，更新 execution_step_logs.sub_step_results_json
  │   │   ├─ 每个sub-step推送WS到前端
  │   │   └─ 等待workflow完成或失败
  │   ├─ type=sampler:
  │   │   ├─ 调用制样机接口
  │   │   └─ 等待完成或失败
  │   └─ type=delay:
  │       └─ asyncio.sleep
  │
  ├─ 3. 检查报警：如果收到 critical 级别报警 → 立即 cancel
  │
  ├─ 4. 完成后更新 task_execution (status=completed/failed/cancelled)
  │
  └─ 5. 通过 WS 推送执行完成通知到前端
```

### 2.6 状态监控模块

- 启动时连接所有已注册机器人的WS (`ws_url`)
- 接收 status/log/alarm/workflow_step 帧
- status帧 → 更新 robot_status 表 + 推送到前端
- log帧 → 写入 operation_logs 表 + 推送到前端
- alarm帧 → 写入 alarms 表 + 触发报警规则检查 + 推送到前端
- 定期HTTP轮询作为WS断线fallback
- 制样机状态独立轮询

### 2.7 报警模块

报警规则引擎：
- 解析 `condition_json`，支持条件：字段阈值（如 `battery < 20`）、连续失败次数、连接断开等
- warning级别 → 记录 + WS推送前端
- critical级别 → 记录 + WS推送前端 + 触发任务执行引擎的紧急停止

报警处理流程：
- 新建报警 → unack
- 操作员确认 → acked，记录确认人和时间
- 推送接口预留（`POST /api/v1/dispatch/alarms/push` 暂时空出）

### 2.8 前端页面

Vue 3 + Element Plus，工业风格。

```
调 度 系 统
├── 状态显示 (/)          — 机器人状态卡片、制样机状态卡片
├── 制样机控制 (/sampler)  — 功能待定，预留页面框架
├── 任务编排 (/tasks/editor)   — 任务模板CRUD，步骤编排界面
├── 任务执行 (/tasks/execution) — 手动触发、L2监听、子任务实时进度、机器人子任务直接调用
├── 报警页面 (/alarms)     — 报警列表+筛选、确认操作、规则配置
└── 运行日志 (/logs)       — 日志列表+筛选、实时滚动
```

---

## 三、模拟控制系统

独立Python进程，模拟控制系统的HTTP API + WebSocket推送。

### 3.1 目录结构

```
dispatch/backend/app/mock/
├── __init__.py
├── robot_mock.py        # 模拟控制系统HTTP+WS服务
├── sampler_mock.py      # 模拟制样机HTTP+WS服务
└── config.py            # 模拟配置（异常概率、延迟等）
```

### 3.2 模拟控制系统

启动独立的HTTP+WS服务（如端口9001）。

#### HTTP API
- `POST /api/v1/robot/{robot_id}/workflows/{name}/execute` — 接收执行请求，返回 `{execution_id, status: "started"}`
- `POST /api/v1/robot/{robot_id}/workflows/{name}/cancel` — 取消执行
- `GET /api/v1/robot/{robot_id}/workflows/executions/{execution_id}` — 查询状态
- `GET /api/v1/robot/{robot_id}/status` — 返回随机状态数据
- 其他控制接口（arm/navigation/upper_body等）返回mock成功

#### WebSocket推送
- `/ws/v1/status` — 定时推送随机状态数据（位置微调、电量波动等）
- `/ws/v1/logs` — 定时推送模拟日志
- workflow_step帧 — 执行workflow时，每个step sleep模拟延迟后推送

#### 可配置项
```python
class MockConfig:
    status_interval: float = 5.0         # 状态推送间隔
    step_duration: tuple = (1.0, 5.0)   # 每个step模拟耗时范围
    alarm_probability: float = 0.15      # 每个step产生报警的概率
    critical_alarm_ratio: float = 0.3    # 报警中严重的比例
    error_probability: float = 0.05      # step执行失败的概率
```

### 3.3 模拟制样机

独立HTTP+WS服务（如端口9002）。

#### HTTP API
- `POST /api/v1/sampler/command` — 接收指令，sleep后返回状态
- `GET /api/v1/sampler/status` — 返回当前状态

#### WebSocket推送
- 定时推送状态更新（进度变化）
- 随机产生报警

---

## 四、共享包新增 (shared/)

### 4.1 protocol/ws_frames.py 新增

```python
class WorkflowStepPayload(BaseModel):
    workflow_name: str
    execution_id: str
    step_id: str
    step_index: int
    total_steps: int
    status: Literal["running", "completed", "failed", "cancelled"]
    message: str = ""
    data: dict = {}

class WorkflowStepFrame(BaseModel):
    type: WsFrameType = "workflow_step"
    robot_id: str
    timestamp: Optional[int] = None
    payload: WorkflowStepPayload

class AlarmPayload(BaseModel):
    alarm_id: str
    level: Literal["warning", "critical"]
    category: str
    title: str
    message: str
    source: str

class AlarmFrame(BaseModel):
    type: WsFrameType = "alarm"
    robot_id: str
    timestamp: Optional[int] = None
    payload: AlarmPayload
```

`WsFrameType` 新增 `WORKFLOW_STEP = "workflow_step"` 和 `ALARM = "alarm"`。

### 4.2 models/workflow.py 新增

```python
class WorkflowExecuteResponse(BaseModel):
    execution_id: str
    status: Literal["started", "running", "completed", "failed", "cancelled"]
    message: str = ""
    step_results: list[StepResult] = []
    error_step_id: Optional[str] = None
```

---

## 五、实现顺序

1. **共享包** — 新增 WS 帧类型和数据模型
2. **控制系统新增** — workflow异步执行 + step推送 + 取消接口 + alarm推送
3. **调度系统后端** — 数据库schema + 各模块API + 任务执行引擎 + 状态监控 + 报警 + 日志
4. **调度系统前端** — 页面重构 + WS实时更新
5. **模拟系统** — 模拟控制系统 + 模拟制样机
6. **测试** — 集成测试 + 端到端测试（使用模拟器）
