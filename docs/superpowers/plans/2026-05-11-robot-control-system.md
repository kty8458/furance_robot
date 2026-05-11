# 机器人控制系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现机器人控制系统的完整后端，包含ROS2 Bridge、HTTP API、WebSocket状态上报、实时日志推送、示教功能

**Architecture:** FastAPI后端分层架构：API层(路由) → Service层(业务逻辑) → ROS2 Bridge层(硬件交互)。WebSocket分两个端点：/ws/v1/status推送到调度系统，/ws/v1/logs推送到前端。

**Tech Stack:** FastAPI, Pydantic v2, websockets, rclpy(ROS2), pytest-asyncio

**前置:** 项目基础计划已完成（shared包、工程约束已就位）

---

## File Structure

```
robot_control/backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI应用入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # 配置加载
│   │   └── lifecycle.py           # 应用生命周期管理
│   ├── api/
│   │   ├── __init__.py
│   │   ├── robot.py               # 机器人控制路由
│   │   ├── arm.py                 # 手臂运控+示教路由
│   │   ├── navigation.py          # 导航路由
│   │   └── ros2_nodes.py          # ROS2节点管理路由
│   ├── ws/
│   │   ├── __init__.py
│   │   ├── status.py              # 状态上报WS端点
│   │   └── logs.py                # 日志推送WS端点
│   ├── ros2/
│   │   ├── __init__.py
│   │   ├── service_client.py      # ROS2 Service客户端封装
│   │   ├── topic_listener.py      # ROS2 Topic监听
│   │   └── log_collector.py       # ROS2日志采集(/rosout)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── robot_service.py       # 机器人指令业务逻辑
│   │   ├── arm_service.py         # 手臂运控+示教
│   │   ├── status_service.py      # 状态聚合与推送
│   │   ├── log_service.py         # 日志采集与分发
│   │   └── ros2_manager.py        # ROS2节点管理
│   └── models/
│       ├── __init__.py
│       └── teach.py               # 示教数据模型
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # 测试fixtures
│   ├── test_config.py
│   ├── test_robot_api.py
│   ├── test_arm_api.py
│   ├── test_navigation_api.py
│   ├── test_ros2_nodes_api.py
│   ├── test_arm_service.py
│   ├── test_status_service.py
│   └── test_log_service.py
└── pyproject.toml
```

---

### Task 1: 配置加载

**Files:**
- Create: `robot_control/backend/app/core/__init__.py`
- Create: `robot_control/backend/app/core/config.py`
- Create: `robot_control/backend/tests/test_config.py`

- [ ] **Step 1: 写配置测试**

创建 `robot_control/backend/app/core/__init__.py`:

```python
```

创建 `robot_control/backend/tests/test_config.py`:

```python
import pytest
from app.core.config import Settings


def test_default_settings():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8000
    assert s.ros2_domain_id == 0
    assert s.ros2_service_timeout == 30.0
    assert s.ws_status_interval == 30
    assert s.log_level == "INFO"
    assert s.log_retention_days == 30


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SERVER_PORT", "9000")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.server_port == 9000
    assert s.log_level == "DEBUG"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd robot_control/backend && python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: 实现配置**

创建 `robot_control/backend/app/core/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    ros2_domain_id: int = 0
    ros2_service_timeout: float = 30.0

    ws_status_interval: int = 30

    log_level: str = "INFO"
    log_dir: str = "/opt/furance_robot/logs"
    log_retention_days: int = 30

    teach_data_dir: str = "/opt/furance_robot/data/teach"

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
```

更新 `robot_control/backend/pyproject.toml` dependencies 添加:

```toml
    "pydantic-settings>=2.2",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd robot_control/backend && pip install -e ".[dev]" && python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add settings configuration"
```

---

### Task 2: ROS2 Service客户端封装（Mock模式）

**Files:**
- Create: `robot_control/backend/app/ros2/__init__.py`
- Create: `robot_control/backend/app/ros2/service_client.py`
- Create: `robot_control/backend/tests/conftest.py`

ROS2在开发环境不可用，Service客户端使用抽象+Mock实现。

- [ ] **Step 1: 写conftest和service_client测试**

创建 `robot_control/backend/app/ros2/__init__.py`:

```python
```

创建 `robot_control/backend/tests/conftest.py`:

```python
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_ros2_client():
    client = AsyncMock()
    client.call_service = AsyncMock(return_value={"success": True, "message": "ok"})
    return client
```

- [ ] **Step 2: 实现ROS2 Service客户端抽象**

创建 `robot_control/backend/app/ros2/service_client.py`:

```python
from abc import ABC, abstractmethod
from typing import Any


class Ros2ServiceClientBase(ABC):
    @abstractmethod
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        ...


class MockRos2ServiceClient(Ros2ServiceClientBase):
    async def call_service(self, service_name: str, request: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "message": "ok"}
```

- [ ] **Step 3: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add ROS2 service client abstraction with mock"
```

---

### Task 3: 机器人控制API

**Files:**
- Create: `robot_control/backend/app/api/__init__.py`
- Create: `robot_control/backend/app/api/robot.py`
- Create: `robot_control/backend/app/services/__init__.py`
- Create: `robot_control/backend/app/services/robot_service.py`
- Create: `robot_control/backend/tests/test_robot_api.py`

- [ ] **Step 1: 写机器人API测试**

创建 `robot_control/backend/app/api/__init__.py`:

```python
```

创建 `robot_control/backend/app/services/__init__.py`:

```python
```

创建 `robot_control/backend/tests/test_robot_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_home_command(client):
    resp = await client.post("/api/v1/robot/robot_001/home")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_grab_command(client):
    resp = await client.post("/api/v1/robot/robot_001/grab", json={"target": "sample_pos"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_place_command(client):
    resp = await client.post("/api/v1/robot/robot_001/place", json={"target": "output_pos"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gripper_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/gripper",
        json={"arm": "left", "action": "close", "force": 50.0},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lift_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/lift",
        json={"direction": "up", "height": 1.5},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_charge_command(client):
    resp = await client.post("/api/v1/robot/robot_001/charge", json={"action": "start"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_enable_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/enable",
        json={"enable": True, "clear_error": True},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_params(client):
    resp = await client.post("/api/v1/robot/robot_001/gripper", json={"arm": "invalid"})
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd robot_control/backend && python -m pytest tests/test_robot_api.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现RobotService**

创建 `robot_control/backend/app/services/robot_service.py`:

```python
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.models.command import (
    HomeCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from app.ros2.service_client import Ros2ServiceClientBase


ROS2_SERVICE_MAP = {
    "home": "/HomeCommand",
    "grab": "/GrabCommand",
    "place": "/PlaceCommand",
    "gripper": "/GripperCommand",
    "lift": "/LiftCommand",
    "charge": "/ChargeCommand",
    "enable": "/EnableCommand",
}


class RobotService:
    def __init__(self, ros2_client: Ros2ServiceClientBase):
        self._ros2 = ros2_client

    async def home(self, robot_id: str) -> ApiResponse:
        result = await self._ros2.call_service("/HomeCommand", {})
        return ApiResponse(data=result)

    async def grab(self, robot_id: str, cmd: GrabCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GrabCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def place(self, robot_id: str, cmd: PlaceCommand) -> ApiResponse:
        result = await self._ros2.call_service("/PlaceCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def gripper(self, robot_id: str, cmd: GripperCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def lift(self, robot_id: str, cmd: LiftCommand) -> ApiResponse:
        result = await self._ros2.call_service("/LiftCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def charge(self, robot_id: str, cmd: ChargeCommand) -> ApiResponse:
        result = await self._ros2.call_service("/ChargeCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def enable(self, robot_id: str, cmd: EnableCommand) -> ApiResponse:
        result = await self._ros2.call_service("/EnableCommand", cmd.model_dump())
        return ApiResponse(data=result)
```

- [ ] **Step 4: 实现机器人路由**

创建 `robot_control/backend/app/api/robot.py`:

```python
from fastapi import APIRouter, Depends
from furance_shared.models.command import (
    GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_service import RobotService
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1/robot/{robot_id}", tags=["robot"])

_ros2_client = MockRos2ServiceClient()
_robot_service = RobotService(_ros2_client)


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str):
    return await _robot_service.home(robot_id)


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand):
    return await _robot_service.grab(robot_id, cmd)


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand):
    return await _robot_service.place(robot_id, cmd)


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand):
    return await _robot_service.gripper(robot_id, cmd)


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand):
    return await _robot_service.lift(robot_id, cmd)


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand):
    return await _robot_service.charge(robot_id, cmd)


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand):
    return await _robot_service.enable(robot_id, cmd)
```

- [ ] **Step 5: 实现应用入口**

创建 `robot_control/backend/app/main.py`:

```python
from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    return app


app = create_app()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd robot_control/backend && python -m pytest tests/test_robot_api.py -v`
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add robot control API and service layer"
```

---

### Task 4: 导航API

**Files:**
- Create: `robot_control/backend/app/api/navigation.py`
- Create: `robot_control/backend/tests/test_navigation_api.py`

- [ ] **Step 1: 写导航API测试**

创建 `robot_control/backend/tests/test_navigation_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_maps(client):
    resp = await client.get("/api/v1/maps")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"]["maps"], list)


@pytest.mark.asyncio
async def test_get_waypoints(client):
    resp = await client.get("/api/v1/maps/map_001/waypoints")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    assert isinstance(data["data"]["waypoints"], list)


@pytest.mark.asyncio
async def test_move_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/move",
        json={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
```

- [ ] **Step 2: 实现导航路由**

创建 `robot_control/backend/app/api/navigation.py`:

```python
from fastapi import APIRouter
from furance_shared.models.command import MoveCommand
from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1", tags=["navigation"])

_ros2_client = MockRos2ServiceClient()


@router.get("/maps", response_model=ApiResponse)
async def get_maps():
    result = await _ros2_client.call_service("/GetMapList", {})
    return ApiResponse(data=result)


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str):
    result = await _ros2_client.call_service("/GetWaypointList", {"map_id": map_id})
    return ApiResponse(data=result)


@router.post("/robot/{robot_id}/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand):
    result = await _ros2_client.call_service("/MoveCommand", cmd.model_dump())
    return ApiResponse(data=result)
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd robot_control/backend && python -m pytest tests/test_navigation_api.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add navigation API (maps, waypoints, move)"
```

---

### Task 5: 手臂运控和示教API

**Files:**
- Create: `robot_control/backend/app/api/arm.py`
- Create: `robot_control/backend/app/services/arm_service.py`
- Create: `robot_control/backend/app/models/__init__.py`
- Create: `robot_control/backend/app/models/teach.py`
- Create: `robot_control/backend/tests/test_arm_api.py`
- Create: `robot_control/backend/tests/test_arm_service.py`

- [ ] **Step 1: 写示教数据模型**

创建 `robot_control/backend/app/models/__init__.py`:

```python
```

创建 `robot_control/backend/app/models/teach.py`:

```python
from pydantic import BaseModel, Field
from furance_shared.models.robot import ArmSide


class TeachPreset(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    joint_angles: list[float] = Field(min_length=7, max_length=7)


class TeachPresetSummary(BaseModel):
    arm: ArmSide
    name: str
```

- [ ] **Step 2: 写ArmService测试**

创建 `robot_control/backend/tests/test_arm_service.py`:

```python
import pytest
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from furance_shared.models.robot import ArmSide


@pytest.fixture
def arm_service(tmp_path):
    return ArmService(teach_dir=str(tmp_path))


def test_save_and_list_teach(arm_service):
    preset = TeachPreset(
        arm=ArmSide.LEFT, name="grab_pos", joint_angles=[0.0] * 7
    )
    arm_service.save_teach("robot_001", preset)
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 1
    assert presets[0].name == "grab_pos"
    assert presets[0].arm == "left"


def test_list_teach_empty(arm_service):
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 0


def test_delete_teach(arm_service):
    preset = TeachPreset(
        arm=ArmSide.LEFT, name="grab_pos", joint_angles=[0.0] * 7
    )
    arm_service.save_teach("robot_001", preset)
    arm_service.delete_teach("robot_001", "grab_pos")
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 0


def test_delete_nonexistent_teach(arm_service):
    arm_service.delete_teach("robot_001", "nonexistent")
    # should not raise
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd robot_control/backend && python -m pytest tests/test_arm_service.py -v`
Expected: FAIL

- [ ] **Step 4: 实现ArmService**

创建 `robot_control/backend/app/services/arm_service.py`:

```python
import json
from pathlib import Path
from furance_shared.models.robot import ArmSide
from furance_shared.utils.errors import BusinessError, ErrorCode
from app.models.teach import TeachPreset, TeachPresetSummary
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse


class ArmService:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None, teach_dir: str = "/opt/furance_robot/data/teach"):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._teach_dir = Path(teach_dir)

    async def arm_move(self, robot_id: str, cmd: ArmMoveCommand) -> ApiResponse:
        result = await self._ros2.call_service("/ArmMoveCommand", cmd.model_dump())
        return ApiResponse(data=result)

    def save_teach(self, robot_id: str, preset: TeachPreset) -> None:
        robot_dir = self._teach_dir / robot_id
        robot_dir.mkdir(parents=True, exist_ok=True)
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)
        key = f"{preset.arm.value}_{preset.name}"
        if key in presets:
            raise BusinessError(
                message=f"Teach preset '{preset.name}' already exists for {preset.arm}",
                code=ErrorCode.TEACH_NAME_EXISTS,
            )
        presets[key] = preset.model_dump()
        file_path.write_text(json.dumps(presets, indent=2))

    def list_teach(self, robot_id: str) -> list[TeachPresetSummary]:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        if not file_path.exists():
            return []
        presets = self._load_presets(file_path)
        return [
            TeachPresetSummary(arm=v["arm"], name=v["name"])
            for v in presets.values()
        ]

    def delete_teach(self, robot_id: str, name: str) -> None:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        if not file_path.exists():
            return
        presets = self._load_presets(file_path)
        keys_to_delete = [k for k, v in presets.items() if v["name"] == name]
        for k in keys_to_delete:
            del presets[k]
        file_path.write_text(json.dumps(presets, indent=2))

    async def exec_teach(self, robot_id: str, cmd: TeachExecCommand) -> ApiResponse:
        robot_dir = self._teach_dir / robot_id
        file_path = robot_dir / "presets.json"
        presets = self._load_presets(file_path)
        key = f"{cmd.arm.value}_{cmd.name}"
        if key not in presets:
            raise BusinessError(
                message=f"Teach preset '{cmd.name}' not found for {cmd.arm}",
                code=ErrorCode.TEACH_NAME_NOT_FOUND,
            )
        result = await self._ros2.call_service("/ArmTeachExec", cmd.model_dump())
        return ApiResponse(data=result)

    def _load_presets(self, file_path: Path) -> dict:
        if not file_path.exists():
            return {}
        return json.loads(file_path.read_text())
```

- [ ] **Step 5: 运行arm_service测试确认通过**

Run: `cd robot_control/backend && python -m pytest tests/test_arm_service.py -v`
Expected: 4 passed

- [ ] **Step 6: 写手臂API测试**

创建 `robot_control/backend/tests/test_arm_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_arm_move_movej(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/arm/move",
        json={
            "arm": "left",
            "method": "moveJ",
            "joint_angles": [0.0] * 7,
            "coordinate": "base_link",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_arm_teach_save_and_list(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/arm/teach/save",
        json={"arm": "left", "name": "test_preset"},
    )
    assert resp.status_code == 200

    resp = await client.get("/api/v1/robot/robot_001/arm/teach/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
```

- [ ] **Step 7: 实现手臂路由**

创建 `robot_control/backend/app/api/arm.py`:

```python
from fastapi import APIRouter, HTTPException
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from app.ros2.service_client import MockRos2ServiceClient
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/robot/{robot_id}/arm", tags=["arm"])

_settings = get_settings()
_arm_service = ArmService(
    ros2_client=MockRos2ServiceClient(),
    teach_dir=_settings.teach_data_dir,
)


@router.post("/move", response_model=ApiResponse)
async def arm_move(robot_id: str, cmd: ArmMoveCommand):
    return await _arm_service.arm_move(robot_id, cmd)


@router.post("/teach/save", response_model=ApiResponse)
async def teach_save(robot_id: str, cmd: TeachSaveCommand):
    try:
        _arm_service.save_teach(robot_id, TeachPreset(
            arm=cmd.arm, name=cmd.name, joint_angles=[0.0] * 7
        ))
        return ApiResponse(data={"name": cmd.name})
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())


@router.get("/teach/list", response_model=ApiResponse)
async def teach_list(robot_id: str):
    presets = _arm_service.list_teach(robot_id)
    return ApiResponse(data=[p.model_dump() for p in presets])


@router.post("/teach/exec", response_model=ApiResponse)
async def teach_exec(robot_id: str, cmd: TeachExecCommand):
    try:
        return await _arm_service.exec_teach(robot_id, cmd)
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.delete("/teach/{name}", response_model=ApiResponse)
async def teach_delete(robot_id: str, name: str):
    _arm_service.delete_teach(robot_id, name)
    return ApiResponse(data={"deleted": name})
```

- [ ] **Step 8: 运行全部测试确认通过**

Run: `cd robot_control/backend && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 9: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add arm control and teach API"
```

---

### Task 6: ROS2节点管理API

**Files:**
- Create: `robot_control/backend/app/api/ros2_nodes.py`
- Create: `robot_control/backend/app/services/ros2_manager.py`
- Create: `robot_control/backend/tests/test_ros2_nodes_api.py`

- [ ] **Step 1: 写ROS2节点管理测试**

创建 `robot_control/backend/tests/test_ros2_nodes_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_nodes(client):
    resp = await client.get("/api/v1/ros2/nodes")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_start_node(client):
    resp = await client.post("/api/v1/ros2/nodes/move_node/start")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stop_node(client):
    resp = await client.post("/api/v1/ros2/nodes/move_node/stop")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_node_status(client):
    resp = await client.get("/api/v1/ros2/nodes/move_node/status")
    assert resp.status_code == 200
```

- [ ] **Step 2: 实现Ros2Manager**

创建 `robot_control/backend/app/services/ros2_manager.py`:

```python
from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient


class Ros2Manager:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None):
        self._ros2 = ros2_client or MockRos2ServiceClient()

    async def list_nodes(self) -> ApiResponse:
        result = await self._ros2.call_service("/GetNodeList", {})
        return ApiResponse(data=result)

    async def start_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStart", {"node": node_name})
        return ApiResponse(data=result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStop", {"node": node_name})
        return ApiResponse(data=result)

    async def node_status(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStatus", {"node": node_name})
        return ApiResponse(data=result)
```

- [ ] **Step 3: 实现ROS2节点路由**

创建 `robot_control/backend/app/api/ros2_nodes.py`:

```python
from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.ros2_manager import Ros2Manager
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1/ros2/nodes", tags=["ros2"])

_ros2_manager = Ros2Manager(MockRos2ServiceClient())


@router.get("", response_model=ApiResponse)
async def list_nodes():
    return await _ros2_manager.list_nodes()


@router.post("/{node_name}/start", response_model=ApiResponse)
async def start_node(node_name: str):
    return await _ros2_manager.start_node(node_name)


@router.post("/{node_name}/stop", response_model=ApiResponse)
async def stop_node(node_name: str):
    return await _ros2_manager.stop_node(node_name)


@router.get("/{node_name}/status", response_model=ApiResponse)
async def node_status(node_name: str):
    return await _ros2_manager.node_status(node_name)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd robot_control/backend && python -m pytest tests/test_ros2_nodes_api.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add ROS2 node management API"
```

---

### Task 7: WebSocket状态上报端点

**Files:**
- Create: `robot_control/backend/app/ws/__init__.py`
- Create: `robot_control/backend/app/ws/status.py`
- Create: `robot_control/backend/app/services/status_service.py`

- [ ] **Step 1: 实现StatusService**

创建 `robot_control/backend/app/ws/__init__.py`:

```python
```

创建 `robot_control/backend/app/services/status_service.py`:

```python
import asyncio
import time
from fastapi import WebSocket
from furance_shared.protocol.ws_frames import StatusFrame, ErrorFrame, WsFrameType
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState


class StatusService:
    def __init__(self):
        self._connections: list[WebSocket] = []

    def add_connection(self, ws: WebSocket):
        self._connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        self._connections.remove(ws)

    async def push_status(self, robot_id: str, status_data: dict):
        frame = StatusFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=status_data,
        )
        await self._broadcast(frame.model_dump())

    async def push_error(self, robot_id: str, error_code: int, error_msg: str, source: str):
        frame = ErrorFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload={"error_code": error_code, "error_msg": error_msg, "source": source},
        )
        await self._broadcast(frame.model_dump())

    async def _broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
```

- [ ] **Step 2: 实现状态WS端点**

创建 `robot_control/backend/app/ws/status.py`:

```python
import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from furance_shared.protocol.ws_frames import StatusFrame
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState
from app.services.status_service import StatusService

router = APIRouter()
_status_service = StatusService()


@router.websocket("/ws/v1/status")
async def status_websocket(websocket: WebSocket):
    await websocket.accept()
    _status_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _status_service.remove_connection(websocket)


def get_status_service() -> StatusService:
    return _status_service
```

- [ ] **Step 3: 注册WS路由到main.py**

更新 `robot_control/backend/app/main.py`:

```python
from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router
from app.ws.status import router as status_ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    app.include_router(status_ws_router)
    return app


app = create_app()
```

- [ ] **Step 4: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add WebSocket status push endpoint"
```

---

### Task 8: WebSocket日志推送端点

**Files:**
- Create: `robot_control/backend/app/ws/logs.py`
- Create: `robot_control/backend/app/services/log_service.py`
- Create: `robot_control/backend/app/ros2/log_collector.py`

- [ ] **Step 1: 实现LogService**

创建 `robot_control/backend/app/services/log_service.py`:

```python
import logging
import time
from fastapi import WebSocket
from furance_shared.protocol.ws_frames import LogFrame


class LogService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._logger = logging.getLogger("robot_control")

    def add_connection(self, ws: WebSocket):
        self._connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def push_log(self, source: str, level: str, message: str, node: str = "backend", robot_id: str = "robot_001"):
        frame = LogFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload={"source": source, "level": level, "node": node, "message": message},
        )
        await self._broadcast(frame.model_dump())

    async def _broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
```

- [ ] **Step 2: 实现日志WS端点**

创建 `robot_control/backend/app/ws/logs.py`:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.log_service import LogService

router = APIRouter()
_log_service = LogService()


@router.websocket("/ws/v1/logs")
async def logs_websocket(websocket: WebSocket):
    await websocket.accept()
    _log_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _log_service.remove_connection(websocket)


def get_log_service() -> LogService:
    return _log_service
```

- [ ] **Step 3: 实现ROS2日志采集器（抽象）**

创建 `robot_control/backend/app/ros2/log_collector.py`:

```python
from abc import ABC, abstractmethod
from app.services.log_service import LogService


class Ros2LogCollectorBase(ABC):
    @abstractmethod
    async def start(self, log_service: LogService):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockRos2LogCollector(Ros2LogCollectorBase):
    async def start(self, log_service: LogService):
        pass

    async def stop(self):
        pass
```

- [ ] **Step 4: 注册日志WS路由到main.py**

更新 `robot_control/backend/app/main.py`:

```python
from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router
from app.ws.status import router as status_ws_router
from app.ws.logs import router as logs_ws_router


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    app.include_router(status_ws_router)
    app.include_router(logs_ws_router)
    return app


app = create_app()
```

- [ ] **Step 5: Commit**

```bash
git add robot_control/
git commit -m "feat(robot-control): add WebSocket log push endpoint and ROS2 log collector"
```

---

### Task 9: 全量测试验证

- [ ] **Step 1: 运行全量测试**

Run: `cd robot_control/backend && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 2: 运行shared包测试确保无回归**

Run: `cd shared && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 3: 运行ruff检查**

Run: `ruff check shared/ robot_control/backend/ && ruff format --check shared/ robot_control/backend/`
Expected: no issues

---

## Self-Review

**1. Spec coverage:**
- HTTP接口(导航/上肢/升降充电使能/手臂运控/示教/ROS2管理) ✓ Tasks 3-6
- WebSocket状态上报 ✓ Task 7
- WebSocket日志推送 ✓ Task 8
- ROS2 Service抽象 ✓ Task 2
- 示教数据本地存储 ✓ Task 5
- 配置管理 ✓ Task 1

**2. Placeholder scan:** 无TBD/TODO。

**3. Type consistency:**
- ArmMoveCommand中method枚举与shared包定义一致 ✓
- GripperCommand arm/force字段与shared包一致 ✓
- StatusFrame/ErrorFrame/LogFrame使用shared包定义 ✓

**注意:** 前端部分(Vue 3)将在控制系统后端稳定后单独实现，不在此计划中。部署脚本(systemd/PyInstaller)将在集成阶段实现。
