# 项目基础 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立项目工程基础，包含工程约束配置、共享协议包、项目目录脚手架

**Architecture:** Monorepo结构，shared/作为Python共享包提供协议定义和数据模型，robot_control/和dispatch/分别作为两个子系统。工程约束通过CLAUDE.md、linter、hooks、settings.json统一管理。

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, Ruff(linter), pytest

---

## File Structure

```
furance_robot/
├── CLAUDE.md                          # 项目工程约束
├── .claude/
│   └── settings.json                  # Claude Code权限配置
├── .github/
│   └── workflows/
│       └── ci.yml                     # CI流水线
├── shared/
│   ├── pyproject.toml                 # 共享包配置
│   ├── src/
│   │   └── furance_shared/
│   │       ├── __init__.py
│   │       ├── models/
│   │       │   ├── __init__.py
│   │       │   ├── robot.py           # 机器人相关数据模型
│   │       │   ├── command.py         # 指令数据模型
│   │       │   └── status.py          # 状态数据模型
│   │       ├── protocol/
│   │       │   ├── __init__.py
│   │       │   ├── ws_frames.py       # WebSocket电文定义
│   │       │   └── http_schema.py     # HTTP请求/响应Schema
│   │       └── utils/
│   │           ├── __init__.py
│   │           ├── logging.py         # 统一日志配置
│   │           └── errors.py          # 统一错误码和异常
│   └── tests/
│       ├── __init__.py
│       ├── test_robot.py
│       ├── test_command.py
│       ├── test_status.py
│       ├── test_ws_frames.py
│       ├── test_http_schema.py
│       └── test_errors.py
├── robot_control/
│   ├── backend/
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   └── __init__.py
│   │   └── tests/
│   │       └── __init__.py
│   ├── frontend/
│   │   ├── package.json
│   │   └── src/
│   └── deploy/
│       └── config.yaml
├── dispatch/
│   ├── backend/
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   └── __init__.py
│   │   └── tests/
│   │       └── __init__.py
│   ├── frontend/
│   │   ├── package.json
│   │   └── src/
│   └── deploy/
│       └── config.yaml
├── docs/
├── ruff.toml                          # Linter配置
├── .pre-commit-config.yaml            # Pre-commit hooks
└── .gitignore
```

---

### Task 1: 项目目录脚手架

**Files:**
- Create: `robot_control/backend/pyproject.toml`
- Create: `robot_control/backend/app/__init__.py`
- Create: `robot_control/backend/tests/__init__.py`
- Create: `dispatch/backend/pyproject.toml`
- Create: `dispatch/backend/app/__init__.py`
- Create: `dispatch/backend/tests/__init__.py`
- Create: `robot_control/deploy/config.yaml`
- Create: `dispatch/deploy/config.yaml`
- Create: `robot_control/frontend/package.json`
- Create: `dispatch/frontend/package.json`
- Modify: `.gitignore`

- [ ] **Step 1: 创建后端目录结构和pyproject.toml**

创建 `robot_control/backend/pyproject.toml`:

```toml
[project]
name = "robot-control"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.5",
    "websockets>=12.0",
    "furance-shared",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

创建 `dispatch/backend/pyproject.toml`:

```toml
[project]
name = "dispatch"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "pydantic>=2.5",
    "websockets>=12.0",
    "aiosqlite>=0.20",
    "furance-shared",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["app*"]
```

创建空 `__init__.py` 文件:
- `robot_control/backend/app/__init__.py`
- `robot_control/backend/tests/__init__.py`
- `dispatch/backend/app/__init__.py`
- `dispatch/backend/tests/__init__.py`

- [ ] **Step 2: 创建部署配置文件**

创建 `robot_control/deploy/config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

ros2:
  domain_id: 0
  service_timeout: 30.0

websocket:
  status_interval: 30  # 心跳间隔(秒)

logging:
  level: "INFO"
  dir: "/opt/furance_robot/logs"
  retention_days: 30

teach:
  data_dir: "/opt/furance_robot/data/teach"
```

创建 `dispatch/deploy/config.yaml`:

```yaml
server:
  host: "0.0.0.0"
  port: 8000

robots:
  - id: "robot_001"
    name: "1号机器人"
    control_url: "http://192.168.1.100:8000"
    ws_url: "ws://192.168.1.100:8000/ws/v1/status"

sampler:
  ws_url: "ws://192.168.1.200:9000"

l2:
  enabled: false
  adapter: "default"

database:
  path: "./data/dispatch.db"

logging:
  level: "INFO"
  dir: "C:\\FuranceDispatch\\logs"
  retention_days: 30
```

- [ ] **Step 3: 创建前端package.json**

创建 `robot_control/frontend/package.json`:

```json
{
  "name": "robot-control-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0",
    "vite": "^5.4"
  }
}
```

创建 `dispatch/frontend/package.json`:

```json
{
  "name": "dispatch-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0",
    "vite": "^5.4"
  }
}
```

- [ ] **Step 4: 更新.gitignore**

```text
.superpowers/
__pycache__/
*.pyc
*.pyo
*.egg-info/
dist/
build/
.venv/
node_modules/
*.db
*.log
.env
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: scaffold project directory structure"
```

---

### Task 2: Linter和代码规范配置

**Files:**
- Create: `ruff.toml`
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: 创建ruff配置**

创建 `ruff.toml`:

```toml
target-version = "py310"
line-length = 120

[lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
]
ignore = ["E501"]

[lint.isort]
known-first-party = ["app", "furance_shared"]

[format]
quote-style = "double"
indent-style = "space"
```

- [ ] **Step 2: 创建pre-commit配置**

创建 `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

- [ ] **Step 3: Commit**

```bash
git add ruff.toml .pre-commit-config.yaml
git commit -m "chore: add ruff linter and pre-commit hooks"
```

---

### Task 3: 共享包 — 错误码与异常定义

**Files:**
- Create: `shared/pyproject.toml`
- Create: `shared/src/furance_shared/__init__.py`
- Create: `shared/src/furance_shared/utils/__init__.py`
- Create: `shared/src/furance_shared/utils/errors.py`
- Create: `shared/tests/__init__.py`
- Create: `shared/tests/test_errors.py`

- [ ] **Step 1: 创建shared包pyproject.toml**

创建 `shared/pyproject.toml`:

```toml
[project]
name = "furance-shared"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.5",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["src"]
```

创建 `shared/src/furance_shared/__init__.py`:

```python
```

创建 `shared/src/furance_shared/utils/__init__.py`:

```python
```

创建 `shared/tests/__init__.py`:

```python
```

- [ ] **Step 2: 写错误码测试**

创建 `shared/tests/test_errors.py`:

```python
import pytest

from furance_shared.utils.errors import (
    ErrorCode,
    FuranceError,
    CommError,
    HardwareError,
    BusinessError,
)


def test_error_code_ranges():
    assert ErrorCode.ROS2_TIMEOUT >= 1000
    assert ErrorCode.ROS2_TIMEOUT < 2000
    assert ErrorCode.MOVE_FAILED >= 2000
    assert ErrorCode.MOVE_FAILED < 3000
    assert ErrorCode.TASK_CONFLICT >= 3000
    assert ErrorCode.TASK_CONFLICT < 4000


def test_furance_error_fields():
    err = FuranceError(code=ErrorCode.ROS2_TIMEOUT, message="timeout")
    assert err.code == 1001
    assert err.message == "timeout"


def test_comm_error():
    err = CommError(message="ws disconnected")
    assert err.code >= 1000
    assert err.code < 2000


def test_hardware_error():
    err = HardwareError(message="move failed")
    assert err.code >= 2000
    assert err.code < 3000


def test_business_error():
    err = BusinessError(message="task conflict")
    assert err.code >= 3000
    assert err.code < 4000


def test_error_to_dict():
    err = FuranceError(code=ErrorCode.ROS2_TIMEOUT, message="timeout")
    d = err.to_dict()
    assert d == {"code": 1001, "message": "timeout"}
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd shared && python -m pytest tests/test_errors.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 4: 实现错误码和异常**

创建 `shared/src/furance_shared/utils/errors.py`:

```python
from enum import IntEnum


class ErrorCode(IntEnum):
    # 通讯类 1xxx
    ROS2_TIMEOUT = 1001
    WS_DISCONNECTED = 1002
    HTTP_REQUEST_FAILED = 1003

    # 硬件类 2xxx
    MOVE_FAILED = 2001
    GRIPPER_ERROR = 2002
    LIFT_ERROR = 2003
    ARM_ERROR = 2004
    CHARGE_ERROR = 2005

    # 业务类 3xxx
    TASK_CONFLICT = 3001
    INVALID_PARAMS = 3002
    NODE_NOT_FOUND = 3003
    TEACH_NAME_EXISTS = 3004
    TEACH_NAME_NOT_FOUND = 3005


class FuranceError(Exception):
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")

    def to_dict(self) -> dict:
        return {"code": int(self.code), "message": self.message}


class CommError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.ROS2_TIMEOUT):
        super().__init__(code=code, message=message)


class HardwareError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.MOVE_FAILED):
        super().__init__(code=code, message=message)


class BusinessError(FuranceError):
    def __init__(self, message: str, code: ErrorCode = ErrorCode.TASK_CONFLICT):
        super().__init__(code=code, message=message)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd shared && pip install -e . && python -m pytest tests/test_errors.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add shared/
git commit -m "feat(shared): add error codes and exception hierarchy"
```

---

### Task 4: 共享包 — 机器人数据模型

**Files:**
- Create: `shared/src/furance_shared/models/__init__.py`
- Create: `shared/src/furance_shared/models/robot.py`
- Create: `shared/tests/test_robot.py`

- [ ] **Step 1: 写机器人模型测试**

创建 `shared/src/furance_shared/models/__init__.py`:

```python
```

创建 `shared/tests/test_robot.py`:

```python
from furance_shared.models.robot import (
    ArmSide,
    GripperAction,
    GripperState,
    LiftDirection,
    ChargeAction,
    RobotStatus,
    ArmState,
    GripperInfo,
    Position,
)


def test_arm_side_values():
    assert ArmSide.LEFT == "left"
    assert ArmSide.RIGHT == "right"


def test_gripper_action_values():
    assert GripperAction.OPEN == "open"
    assert GripperAction.CLOSE == "close"


def test_gripper_state_values():
    assert GripperState.OPEN == "open"
    assert GripperState.CLOSED == "closed"


def test_lift_direction_values():
    assert LiftDirection.UP == "up"
    assert LiftDirection.DOWN == "down"


def test_charge_action_values():
    assert ChargeAction.START == "start"
    assert ChargeAction.STOP == "stop"


def test_position():
    pos = Position(x=1.0, y=2.0, theta=0.5)
    assert pos.x == 1.0
    assert pos.y == 2.0
    assert pos.theta == 0.5


def test_gripper_info():
    info = GripperInfo(state=GripperState.OPEN, force=50.0)
    assert info.state == "open"
    assert info.force == 50.0


def test_arm_state():
    arm = ArmState(joint_angles=[0.0] * 7, status="idle")
    assert len(arm.joint_angles) == 7
    assert arm.status == "idle"


def test_robot_status():
    status = RobotStatus(
        position=Position(x=1.0, y=2.0, theta=0.5),
        current_map="map_001",
        lift_height=0.3,
        gripper={
            "left": GripperInfo(state=GripperState.OPEN, force=0.0),
            "right": GripperInfo(state=GripperState.CLOSED, force=50.0),
        },
        battery=85,
        charging=False,
        enabled=True,
        error_code=0,
        task_status="idle",
        arm={
            "left": ArmState(joint_angles=[0.0] * 7, status="idle"),
            "right": ArmState(joint_angles=[0.0] * 7, status="idle"),
        },
    )
    assert status.battery == 85
    assert status.gripper["left"].state == "open"
    assert status.arm["right"].status == "idle"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd shared && python -m pytest tests/test_robot.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现机器人模型**

创建 `shared/src/furance_shared/models/robot.py`:

```python
from enum import StrEnum
from typing import Dict

from pydantic import BaseModel, Field


class ArmSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class GripperAction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


class GripperState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class LiftDirection(StrEnum):
    UP = "up"
    DOWN = "down"


class ChargeAction(StrEnum):
    START = "start"
    STOP = "stop"


class Position(BaseModel):
    x: float
    y: float
    theta: float


class GripperInfo(BaseModel):
    state: GripperState
    force: float = 0.0


class ArmState(BaseModel):
    joint_angles: list[float] = Field(min_length=7, max_length=7)
    status: str = "idle"


class RobotStatus(BaseModel):
    position: Position
    current_map: str = ""
    lift_height: float = 0.0
    gripper: Dict[str, GripperInfo]
    battery: int = 0
    charging: bool = False
    enabled: bool = False
    error_code: int = 0
    task_status: str = "idle"
    arm: Dict[str, ArmState]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd shared && python -m pytest tests/test_robot.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add shared/
git commit -m "feat(shared): add robot data models (enums, position, status)"
```

---

### Task 5: 共享包 — 指令数据模型

**Files:**
- Create: `shared/src/furance_shared/models/command.py`
- Create: `shared/tests/test_command.py`

- [ ] **Step 1: 写指令模型测试**

创建 `shared/tests/test_command.py`:

```python
from furance_shared.models.command import (
    MoveCommand,
    GrabCommand,
    PlaceCommand,
    GripperCommand,
    LiftCommand,
    ChargeCommand,
    EnableCommand,
    HomeCommand,
    ArmMoveCommand,
    ArmMoveMethod,
    TeachSaveCommand,
    TeachExecCommand,
)


def test_move_command():
    cmd = MoveCommand(map_id="map_001", waypoint_id="wp_01", speed=0.5)
    assert cmd.map_id == "map_001"
    assert cmd.waypoint_id == "wp_01"
    assert cmd.speed == 0.5


def test_grab_command():
    cmd = GrabCommand(target="sample_pos")
    assert cmd.target == "sample_pos"


def test_place_command():
    cmd = PlaceCommand(target="sampler_input")
    assert cmd.target == "sampler_input"


def test_gripper_command_with_force():
    cmd = GripperCommand(arm="left", action="close", force=50.0)
    assert cmd.arm == "left"
    assert cmd.force == 50.0


def test_gripper_command_without_force():
    cmd = GripperCommand(arm="right", action="open")
    assert cmd.force == 0.0


def test_lift_command():
    cmd = LiftCommand(direction="up", height=1.5)
    assert cmd.direction == "up"
    assert cmd.height == 1.5


def test_charge_command():
    cmd = ChargeCommand(action="start")
    assert cmd.action == "start"


def test_enable_command():
    cmd = EnableCommand(enable=True, clear_error=True)
    assert cmd.enable is True
    assert cmd.clear_error is True


def test_home_command():
    cmd = HomeCommand()
    assert isinstance(cmd, HomeCommand)


def test_arm_move_command_movej():
    cmd = ArmMoveCommand(
        arm="left",
        method=ArmMoveMethod.MOVEJ,
        joint_angles=[0.0] * 7,
        coordinate="base_link",
    )
    assert cmd.method == "moveJ"
    assert cmd.position is None


def test_arm_move_command_movep():
    cmd = ArmMoveCommand(
        arm="right",
        method=ArmMoveMethod.MOVEP,
        position={"x": 0.1, "y": 0.2, "z": 0.3, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        coordinate="base_link",
    )
    assert cmd.joint_angles is None
    assert cmd.position is not None


def test_teach_save_command():
    cmd = TeachSaveCommand(arm="left", name="grab_pos")
    assert cmd.name == "grab_pos"


def test_teach_exec_command():
    cmd = TeachExecCommand(arm="left", name="grab_pos")
    assert cmd.name == "grab_pos"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd shared && python -m pytest tests/test_command.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现指令模型**

创建 `shared/src/furance_shared/models/command.py`:

```python
from enum import StrEnum
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator

from furance_shared.models.robot import ArmSide, GripperAction, LiftDirection, ChargeAction


class ArmMoveMethod(StrEnum):
    MOVEP = "movep"
    MOVEL = "moveL"
    MOVEJ = "moveJ"


class MoveCommand(BaseModel):
    map_id: str
    waypoint_id: str
    speed: float = Field(gt=0, le=2.0)


class GrabCommand(BaseModel):
    target: str


class PlaceCommand(BaseModel):
    target: str


class GripperCommand(BaseModel):
    arm: ArmSide
    action: GripperAction
    force: float = Field(default=0.0, ge=0)


class LiftCommand(BaseModel):
    direction: LiftDirection
    height: float = Field(gt=0)


class ChargeCommand(BaseModel):
    action: ChargeAction


class EnableCommand(BaseModel):
    enable: bool
    clear_error: bool


class HomeCommand(BaseModel):
    pass


class ArmMoveCommand(BaseModel):
    arm: ArmSide
    method: ArmMoveMethod
    joint_angles: Optional[list[float]] = Field(default=None, min_length=7, max_length=7)
    position: Optional[Dict[str, float]] = None
    coordinate: str = "base_link"

    @model_validator(mode="after")
    def validate_method_params(self):
        if self.method in (ArmMoveMethod.MOVEP, ArmMoveMethod.MOVEL):
            if self.position is None:
                raise ValueError(f"{self.method} requires position")
        if self.method == ArmMoveMethod.MOVEJ:
            if self.joint_angles is None:
                raise ValueError("moveJ requires joint_angles")
        return self


class TeachSaveCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)


class TeachExecCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd shared && python -m pytest tests/test_command.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add shared/
git commit -m "feat(shared): add command data models (move, grab, gripper, arm, teach)"
```

---

### Task 6: 共享包 — HTTP请求/响应Schema

**Files:**
- Create: `shared/src/furance_shared/protocol/__init__.py`
- Create: `shared/src/furance_shared/protocol/http_schema.py`
- Create: `shared/tests/test_http_schema.py`

- [ ] **Step 1: 写HTTP Schema测试**

创建 `shared/src/furance_shared/protocol/__init__.py`:

```python
```

创建 `shared/tests/test_http_schema.py`:

```python
from furance_shared.protocol.http_schema import ApiResponse, ErrorResponse


def test_api_response_success():
    resp = ApiResponse(data={"task_id": "123"})
    assert resp.code == 0
    assert resp.message == "ok"
    assert resp.data == {"task_id": "123"}


def test_api_response_custom_message():
    resp = ApiResponse(code=0, message="created", data=None)
    assert resp.message == "created"
    assert resp.data is None


def test_error_response():
    resp = ErrorResponse(code=1001, message="ROS2 timeout")
    assert resp.code == 1001
    assert resp.data is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd shared && python -m pytest tests/test_http_schema.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现HTTP Schema**

创建 `shared/src/furance_shared/protocol/http_schema.py`:

```python
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    code: int
    message: str
    data: None = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd shared && python -m pytest tests/test_http_schema.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add shared/
git commit -m "feat(shared): add HTTP request/response schemas"
```

---

### Task 7: 共享包 — WebSocket电文定义

**Files:**
- Create: `shared/src/furance_shared/protocol/ws_frames.py`
- Create: `shared/tests/test_ws_frames.py`

- [ ] **Step 1: 写WS电文测试**

创建 `shared/tests/test_ws_frames.py`:

```python
from furance_shared.protocol.ws_frames import (
    WsFrameType,
    StatusPayload,
    ErrorPayload,
    LogPayload,
    StatusFrame,
    ErrorFrame,
    LogFrame,
)
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState


def test_status_frame():
    frame = StatusFrame(
        robot_id="robot_001",
        payload=StatusPayload(
            position=Position(x=1.0, y=2.0, theta=0.5),
            current_map="map_001",
            gripper={
                "left": GripperInfo(state=GripperState.OPEN, force=0.0),
                "right": GripperInfo(state=GripperState.CLOSED, force=50.0),
            },
            arm={
                "left": ArmState(joint_angles=[0.0] * 7, status="idle"),
                "right": ArmState(joint_angles=[0.0] * 7, status="idle"),
            },
        ),
    )
    assert frame.type == WsFrameType.STATUS
    assert frame.robot_id == "robot_001"
    assert frame.payload.battery == 0


def test_error_frame():
    frame = ErrorFrame(
        robot_id="robot_001",
        payload=ErrorPayload(
            error_code=2001,
            error_msg="Move failed",
            source="move_node",
        ),
    )
    assert frame.type == WsFrameType.ERROR
    assert frame.payload.error_code == 2001


def test_log_frame():
    frame = LogFrame(
        robot_id="robot_001",
        payload=LogPayload(
            level="info",
            source="move_node",
            message="Navigation goal reached",
        ),
    )
    assert frame.type == WsFrameType.LOG
    assert frame.payload.level == "info"


def test_frame_serialization():
    frame = ErrorFrame(
        robot_id="robot_001",
        payload=ErrorPayload(error_code=1001, error_msg="timeout", source="ros2"),
    )
    data = frame.model_dump()
    assert data["type"] == "error"
    assert data["payload"]["error_code"] == 1001
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd shared && python -m pytest tests/test_ws_frames.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现WS电文**

创建 `shared/src/furance_shared/protocol/ws_frames.py`:

```python
from enum import StrEnum
from typing import Dict, Optional

from pydantic import BaseModel

from furance_shared.models.robot import ArmState, GripperInfo, Position


class WsFrameType(StrEnum):
    STATUS = "status"
    ERROR = "error"
    LOG = "log"


class StatusPayload(BaseModel):
    position: Position
    current_map: str = ""
    lift_height: float = 0.0
    gripper: Dict[str, GripperInfo]
    battery: int = 0
    charging: bool = False
    enabled: bool = False
    error_code: int = 0
    task_status: str = "idle"
    arm: Dict[str, ArmState]
    ros2_nodes: Optional[Dict[str, str]] = None


class ErrorPayload(BaseModel):
    error_code: int
    error_msg: str
    source: str


class LogPayload(BaseModel):
    level: str
    source: str
    message: str


class WsFrame(BaseModel):
    type: WsFrameType
    robot_id: str
    timestamp: Optional[int] = None
    payload: BaseModel


class StatusFrame(BaseModel):
    type: WsFrameType = WsFrameType.STATUS
    robot_id: str
    timestamp: Optional[int] = None
    payload: StatusPayload


class ErrorFrame(BaseModel):
    type: WsFrameType = WsFrameType.ERROR
    robot_id: str
    timestamp: Optional[int] = None
    payload: ErrorPayload


class LogFrame(BaseModel):
    type: WsFrameType = WsFrameType.LOG
    robot_id: str
    timestamp: Optional[int] = None
    payload: LogPayload
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd shared && python -m pytest tests/test_ws_frames.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add shared/
git commit -m "feat(shared): add WebSocket frame definitions (status, error, log)"
```

---

### Task 8: 共享包 — 统一日志配置

**Files:**
- Create: `shared/src/furance_shared/utils/logging.py`
- Create: `shared/src/furance_shared/models/status.py`

- [ ] **Step 1: 实现统一日志配置**

创建 `shared/src/furance_shared/utils/logging.py`:

```python
import logging
import sys
from pathlib import Path


def setup_logging(name: str, level: str = "INFO", log_dir: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.TimedRotatingFileHandler(
            log_path / f"{name}.log",
            when="midnight",
            backupCount=30,
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
```

创建 `shared/src/furance_shared/models/status.py`:

```python
from enum import StrEnum


class TaskStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


class NodeStatus(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class SamplerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    COMPLETED = "completed"
```

- [ ] **Step 2: Commit**

```bash
git add shared/
git commit -m "feat(shared): add logging setup and status enums"
```

---

### Task 9: CLAUDE.md工程约束

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: 创建CLAUDE.md**

创建 `CLAUDE.md`:

```markdown
# Furance Robot - 工程约束

## 项目概述
轮式双臂机器人控制系统和调度系统，Monorepo结构。

## 目录结构
- `shared/` - 共享Python包(furance-shared)，协议定义和数据模型
- `robot_control/` - 机器人控制系统(Ubuntu工控机)
- `dispatch/` - 调度系统(Win10控制柜)

## 开发规范

### Python
- Python 3.10+，使用type hints
- Linter: ruff (配置见 ruff.toml)
- 测试: pytest + pytest-asyncio
- 数据模型: Pydantic v2
- 异步: async/await，禁止同步阻塞调用

### 前端
- Vue 3 + Vite
- 功能性优先，工业风格

### 通讯协议
- HTTP: RESTful，统一响应格式 {code, message, data}
- WebSocket: JSON帧，类型字段区分(status/error/log)
- ROS2: Service模式，统一Request/Response
- 所有协议定义在 shared/src/furance_shared/protocol/

### 错误码
- 1xxx 通讯类
- 2xxx 硬件类
- 3xxx 业务类

### Git
- 提交格式: `<type>: <message>`
- type: feat/fix/chore/docs/refactor/test
- 每个功能点独立提交

## 关键设计决策
- 控制系统是硬件代理层，调度系统是业务逻辑层
- 手臂运控和示教仅暴露在控制系统API上
- 调度系统不直接与ROS2交互
- 示教数据存储在控制系统本地JSON文件
- L2接口预留抽象层，默认禁用

## 测试要求
- 共享包: 100%模型测试覆盖
- 后端: API集成测试 + Service单元测试
- 修改shared包后必须运行全量测试
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add CLAUDE.md engineering constraints"
```

---

### Task 10: Claude Code settings配置

**Files:**
- Create: `.claude/settings.json`

- [ ] **Step 1: 创建settings.json**

创建 `.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python -m pytest:*)",
      "Bash(pip install:*)",
      "Bash(cd shared:*)",
      "Bash(cd robot_control:*)",
      "Bash(cd dispatch:*)",
      "Bash(npm:*)",
      "Bash(ruff:*)",
      "Bash(git add:*)",
      "Bash(git commit:*)",
      "Bash(git status:*)",
      "Bash(git diff:*)",
      "Bash(git log:*)",
      "Bash(ls:*)",
      "Bash(mkdir:*)",
      "Bash(cat:*)",
      "Read",
      "Write",
      "Edit"
    ]
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add .claude/
git commit -m "chore: add Claude Code settings"
```

---

### Task 11: CI流水线

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 创建CI配置**

创建 `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install ruff
      - run: ruff check shared/ robot_control/backend/ dispatch/backend/
      - run: ruff format --check shared/ robot_control/backend/ dispatch/backend/

  test-shared:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: cd shared && pip install -e ".[dev]"
      - run: cd shared && python -m pytest tests/ -v

  test-robot-control:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: cd shared && pip install -e .
      - run: cd robot_control/backend && pip install -e ".[dev]"
      - run: cd robot_control/backend && python -m pytest tests/ -v

  test-dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: cd shared && pip install -e .
      - run: cd dispatch/backend && pip install -e ".[dev]"
      - run: cd dispatch/backend && python -m pytest tests/ -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/
git commit -m "ci: add GitHub Actions CI pipeline (lint + test)"
```

---

## Self-Review

**1. Spec coverage:**
- 错误码体系 ✓ (Task 3)
- 机器人数据模型 ✓ (Task 4)
- 指令数据模型 ✓ (Task 5)
- HTTP响应格式 ✓ (Task 6)
- WebSocket电文格式 ✓ (Task 7)
- 状态枚举 ✓ (Task 8)
- 日志配置 ✓ (Task 8)
- CLAUDE.md ✓ (Task 9)
- settings.json ✓ (Task 10)
- CI ✓ (Task 11)
- Linter ✓ (Task 2)
- 目录脚手架 ✓ (Task 1)

**2. Placeholder scan:** 无TBD/TODO/模糊步骤。

**3. Type consistency:**
- GripperCommand中force字段: Task 5定义 `float = Field(default=0.0, ge=0)`，与spec中"可选，默认0=系统默认"一致 ✓
- ArmMoveCommand中method枚举: movep/moveL/moveJ与spec一致 ✓
- WsFrameType: status/error/log与spec一致 ✓
