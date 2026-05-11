# 调度系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现调度系统完整后端，包含机器人控制代理、任务编排引擎、制样机通讯、L2预留、SQLite数据持久化

**Architecture:** FastAPI后端分层架构：API层 → Service层 → Client层。调度系统作为代理，将机器人指令转发到控制系统，同时管理任务编排和制样机协同。

**Tech Stack:** FastAPI, Pydantic v2, aiosqlite, websockets, pytest-asyncio

**前置:** 项目基础计划 + 机器人控制系统计划已完成

---

## File Structure

```
dispatch/backend/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI应用入口
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py              # 配置加载
│   │   └── database.py            # SQLite数据库初始化
│   ├── api/
│   │   ├── __init__.py
│   │   ├── robot.py               # 机器人控制代理路由
│   │   ├── task.py                # 任务管理路由
│   │   ├── sampler.py             # 制样机控制路由
│   │   ├── status.py              # 状态查询路由
│   │   └── navigation.py          # 导航代理路由
│   ├── services/
│   │   ├── __init__.py
│   │   ├── robot_proxy.py         # 机器人控制代理服务
│   │   ├── status_service.py      # 状态接收与存储
│   │   ├── task_engine.py         # 任务编排引擎
│   │   ├── sampler_service.py     # 制样机控制服务
│   │   └── l2_listener.py         # L2监听(预留)
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── robot_http.py          # 控制系统HTTP客户端
│   │   ├── robot_ws.py            # 控制系统WS客户端
│   │   ├── sampler_ws.py          # 制样机WS客户端
│   │   └── l2_client.py           # L2客户端(预留抽象)
│   └── models/
│       ├── __init__.py
│       └── db.py                  # 数据库模型定义
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_robot_api.py
│   ├── test_task_api.py
│   ├── test_task_engine.py
│   ├── test_sampler_api.py
│   └── test_database.py
└── pyproject.toml
```

---

### Task 1: 配置加载

**Files:**
- Create: `dispatch/backend/app/core/__init__.py`
- Create: `dispatch/backend/app/core/config.py`
- Create: `dispatch/backend/tests/test_config.py`

- [ ] **Step 1: 写配置测试**

创建 `dispatch/backend/app/core/__init__.py`:

```python
```

创建 `dispatch/backend/tests/test_config.py`:

```python
from app.core.config import Settings


def test_default_settings():
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8000
    assert s.l2_enabled is False
    assert s.l2_adapter == "default"


def test_robot_configs():
    s = Settings()
    assert len(s.robots) > 0
    assert s.robots[0].id == "robot_001"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd dispatch/backend && python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: 实现配置**

创建 `dispatch/backend/app/core/config.py`:

```python
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class RobotConfig(BaseModel):
    id: str
    name: str
    control_url: str
    ws_url: str


class SamplerConfig(BaseModel):
    ws_url: str


class L2Config(BaseModel):
    enabled: bool = False
    adapter: str = "default"


class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    robots: list[RobotConfig] = [
        RobotConfig(
            id="robot_001",
            name="1号机器人",
            control_url="http://192.168.1.100:8000",
            ws_url="ws://192.168.1.100:8000/ws/v1/status",
        )
    ]

    sampler: SamplerConfig = SamplerConfig(ws_url="ws://192.168.1.200:9000")

    l2: L2Config = L2Config()

    database_path: str = "./data/dispatch.db"

    log_level: str = "INFO"
    log_dir: str = "C:\\FuranceDispatch\\logs"
    log_retention_days: int = 30

    model_config = {"env_prefix": "", "case_sensitive": False}


def get_settings() -> Settings:
    return Settings()
```

更新 `dispatch/backend/pyproject.toml` dependencies 添加:

```toml
    "pydantic-settings>=2.2",
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd dispatch/backend && pip install -e ".[dev]" && python -m pytest tests/test_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add settings configuration"
```

---

### Task 2: SQLite数据库初始化

**Files:**
- Create: `dispatch/backend/app/core/database.py`
- Create: `dispatch/backend/app/models/__init__.py`
- Create: `dispatch/backend/app/models/db.py`
- Create: `dispatch/backend/tests/test_database.py`

- [ ] **Step 1: 写数据库测试**

创建 `dispatch/backend/app/models/__init__.py`:

```python
```

创建 `dispatch/backend/tests/test_database.py`:

```python
import pytest
from app.core.database import Database


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.init()
    yield database
    await database.close()


@pytest.mark.asyncio
async def test_database_init(db):
    assert db is not None


@pytest.mark.asyncio
async def test_insert_and_query_robot_status(db):
    await db.execute(
        "INSERT INTO robot_status (robot_id, position_json, battery, task_status) VALUES (?, ?, ?, ?)",
        ("robot_001", '{"x":1.0}', 85, "idle"),
    )
    rows = await db.fetch_all("SELECT * FROM robot_status WHERE robot_id = ?", ("robot_001",))
    assert len(rows) == 1
    assert rows[0]["robot_id"] == "robot_001"
    assert rows[0]["battery"] == 85
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd dispatch/backend && python -m pytest tests/test_database.py -v`
Expected: FAIL

- [ ] **Step 3: 实现数据库**

创建 `dispatch/backend/app/core/database.py`:

```python
import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS robots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    control_url TEXT NOT NULL,
    ws_url TEXT NOT NULL,
    status TEXT DEFAULT 'offline',
    last_heartbeat REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_template_id TEXT NOT NULL,
    robot_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS task_step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    action TEXT NOT NULL,
    params_json TEXT,
    result_json TEXT,
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL
);

CREATE TABLE IF NOT EXISTS sampler_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'idle',
    progress INTEGER DEFAULT 0,
    last_update REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    position_json TEXT DEFAULT '{}',
    gripper_json TEXT DEFAULT '{}',
    arm_json TEXT DEFAULT '{}',
    battery INTEGER DEFAULT 0,
    charging INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 0,
    error_code INTEGER DEFAULT 0,
    task_status TEXT DEFAULT 'idle',
    updated_at REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS l2_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    l2_request_id TEXT,
    task_template_id TEXT,
    task_execution_id INTEGER,
    command_json TEXT,
    status TEXT DEFAULT 'pending',
    received_at REAL,
    completed_at REAL,
    response_json TEXT
);
"""


class Database:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def execute(self, query: str, params: tuple = ()):
        await self._db.execute(query, params)
        await self._db.commit()

    async def fetch_all(self, query: str, params: tuple = ()) -> list[dict]:
        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetch_one(self, query: str, params: tuple = ()) -> dict | None:
        cursor = await self._db.execute(query, params)
        row = await cursor.fetchone()
        return dict(row) if row else None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd dispatch/backend && python -m pytest tests/test_database.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add SQLite database with schema and async access layer"
```

---

### Task 3: 机器人控制代理服务

**Files:**
- Create: `dispatch/backend/app/clients/__init__.py`
- Create: `dispatch/backend/app/clients/robot_http.py`
- Create: `dispatch/backend/app/services/__init__.py`
- Create: `dispatch/backend/app/services/robot_proxy.py`
- Create: `dispatch/backend/tests/conftest.py`

- [ ] **Step 1: 实现HTTP客户端**

创建 `dispatch/backend/app/clients/__init__.py`:

```python
```

创建 `dispatch/backend/app/services/__init__.py`:

```python
```

创建 `dispatch/backend/app/clients/robot_http.py`:

```python
import httpx
from furance_shared.protocol.http_schema import ApiResponse


class RobotHttpClient:
    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def post(self, path: str, json: dict | None = None) -> ApiResponse:
        url = f"{self._base_url}{path}"
        resp = await self._client.post(url, json=json)
        resp.raise_for_status()
        return ApiResponse(**resp.json())

    async def get(self, path: str) -> ApiResponse:
        url = f"{self._base_url}{path}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return ApiResponse(**resp.json())

    async def close(self):
        await self._client.aclose()
```

- [ ] **Step 2: 实现RobotProxyService**

创建 `dispatch/backend/app/services/robot_proxy.py`:

```python
from furance_shared.protocol.http_schema import ApiResponse
from app.clients.robot_http import RobotHttpClient
from app.core.config import get_settings


class RobotProxyService:
    def __init__(self):
        self._clients: dict[str, RobotHttpClient] = {}
        settings = get_settings()
        for robot in settings.robots:
            self._clients[robot.id] = RobotHttpClient(robot.control_url)

    async def forward(self, robot_id: str, path: str, json: dict | None = None) -> ApiResponse:
        client = self._clients.get(robot_id)
        if not client:
            return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
        return await client.post(path, json)

    async def forward_get(self, robot_id: str, path: str) -> ApiResponse:
        client = self._clients.get(robot_id)
        if not client:
            return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
        return await client.get(path)

    async def close(self):
        for client in self._clients.values():
            await client.close()
```

- [ ] **Step 3: 写conftest**

创建 `dispatch/backend/tests/conftest.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from furance_shared.protocol.http_schema import ApiResponse


@pytest.fixture
def mock_robot_proxy():
    proxy = AsyncMock()
    proxy.forward = AsyncMock(return_value=ApiResponse(code=0, data={"success": True}))
    proxy.forward_get = AsyncMock(return_value=ApiResponse(code=0, data={}))
    return proxy
```

- [ ] **Step 4: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add robot proxy service and HTTP client"
```

---

### Task 4: 机器人控制代理API

**Files:**
- Create: `dispatch/backend/app/api/__init__.py`
- Create: `dispatch/backend/app/api/robot.py`
- Create: `dispatch/backend/app/api/navigation.py`
- Create: `dispatch/backend/app/main.py`
- Create: `dispatch/backend/tests/test_robot_api.py`

- [ ] **Step 1: 写机器人代理API测试**

创建 `dispatch/backend/app/api/__init__.py`:

```python
```

创建 `dispatch/backend/tests/test_robot_api.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from furance_shared.protocol.http_schema import ApiResponse
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
async def test_robot_home(client):
    resp = await client.post("/api/v1/robot/robot_001/home")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_robot_move(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/move",
        json={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_grab(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/grab",
        json={"target": "sample"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_status(client):
    resp = await client.get("/api/v1/robot/robot_001/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_not_found(client):
    resp = await client.post("/api/v1/robot/robot_999/home")
    assert resp.status_code == 200
    assert resp.json()["code"] != 0
```

- [ ] **Step 2: 实现机器人代理路由**

创建 `dispatch/backend/app/api/robot.py`:

```python
from fastapi import APIRouter
from furance_shared.models.command import (
    MoveCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/robot/{robot_id}", tags=["robot"])

_proxy = RobotProxyService()


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/home")


@router.post("/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/move", cmd.model_dump())


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/grab", cmd.model_dump())


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/place", cmd.model_dump())


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/gripper", cmd.model_dump())


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/lift", cmd.model_dump())


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/charge", cmd.model_dump())


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/enable", cmd.model_dump())


@router.get("/status", response_model=ApiResponse)
async def status(robot_id: str):
    return await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")


@router.get("", response_model=ApiResponse)
async def list_robots():
    return ApiResponse(data=[r.model_dump() for r in _proxy._clients.keys()])
```

- [ ] **Step 3: 实现导航代理路由**

创建 `dispatch/backend/app/api/navigation.py`:

```python
from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1", tags=["navigation"])

_proxy = RobotProxyService()


@router.get("/maps", response_model=ApiResponse)
async def get_maps():
    robot_id = list(_proxy._clients.keys())[0]
    return await _proxy.forward_get(robot_id, "/api/v1/maps")


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str):
    robot_id = list(_proxy._clients.keys())[0]
    return await _proxy.forward_get(robot_id, f"/api/v1/maps/{map_id}/waypoints")
```

- [ ] **Step 4: 实现应用入口**

创建 `dispatch/backend/app/main.py`:

```python
from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.navigation import router as nav_router
from app.api.task import router as task_router
from app.api.sampler import router as sampler_router
from app.api.status import router as status_router


def create_app() -> FastAPI:
    app = FastAPI(title="Dispatch System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(nav_router)
    app.include_router(task_router)
    app.include_router(sampler_router)
    app.include_router(status_router)
    return app


app = create_app()
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd dispatch/backend && python -m pytest tests/test_robot_api.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add robot proxy API and navigation proxy"
```

---

### Task 5: 任务编排引擎

**Files:**
- Create: `dispatch/backend/app/services/task_engine.py`
- Create: `dispatch/backend/app/api/task.py`
- Create: `dispatch/backend/tests/test_task_engine.py`
- Create: `dispatch/backend/tests/test_task_api.py`

- [ ] **Step 1: 写任务引擎测试**

创建 `dispatch/backend/tests/test_task_engine.py`:

```python
import pytest
import json
import time
from app.services.task_engine import TaskEngine, TaskTemplate, TaskStep
from unittest.mock import AsyncMock
from furance_shared.protocol.http_schema import ApiResponse


@pytest.fixture
def task_engine(tmp_path):
    engine = TaskEngine(db_path=str(tmp_path / "test.db"))
    return engine


@pytest.mark.asyncio
async def test_create_template(task_engine):
    await task_engine.init_db()
    template = TaskTemplate(
        id="sample_delivery",
        name="取样送样流程",
        steps=[
            TaskStep(order=1, action="robot.home", params={}),
            TaskStep(order=2, action="robot.move", params={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5}),
        ],
    )
    await task_engine.save_template(template)
    templates = await task_engine.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "取样送样流程"


@pytest.mark.asyncio
async def test_execute_template(task_engine):
    await task_engine.init_db()
    template = TaskTemplate(
        id="simple_home",
        name="归零流程",
        steps=[TaskStep(order=1, action="robot.home", params={})],
    )
    await task_engine.save_template(template)

    mock_proxy = AsyncMock()
    mock_proxy.forward = AsyncMock(return_value=ApiResponse(code=0))
    mock_sampler = AsyncMock()
    mock_sampler.start = AsyncMock(return_value=ApiResponse(code=0))

    result = await task_engine.execute("simple_home", "robot_001", mock_proxy, mock_sampler)
    assert result["status"] == "completed"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd dispatch/backend && python -m pytest tests/test_task_engine.py -v`
Expected: FAIL

- [ ] **Step 3: 实现TaskEngine**

创建 `dispatch/backend/app/services/task_engine.py`:

```python
import json
import time
from pydantic import BaseModel
from app.core.database import Database
from furance_shared.protocol.http_schema import ApiResponse


class TaskStep(BaseModel):
    order: int
    action: str
    params: dict = {}


class TaskTemplate(BaseModel):
    id: str
    name: str
    steps: list[TaskStep]


class TaskEngine:
    def __init__(self, db_path: str = "./data/dispatch.db"):
        self._db = Database(db_path)

    async def init_db(self):
        await self._db.init()

    async def save_template(self, template: TaskTemplate):
        now = time.time()
        await self._db.execute(
            "INSERT OR REPLACE INTO task_templates (id, name, steps_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (template.id, template.name, template.model_dump_json(exclude={"id", "name"}), now, now),
        )

    async def list_templates(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM task_templates")

    async def execute(self, template_id: str, robot_id: str, robot_proxy, sampler_service) -> dict:
        template_row = await self._db.fetch_one(
            "SELECT * FROM task_templates WHERE id = ?", (template_id,)
        )
        if not template_row:
            return {"status": "error", "error_msg": f"Template {template_id} not found"}

        steps_data = json.loads(template_row["steps_json"])
        steps = steps_data.get("steps", [])

        now = time.time()
        await self._db.execute(
            "INSERT INTO task_executions (task_template_id, robot_id, status, started_at) VALUES (?, ?, ?, ?)",
            (template_id, robot_id, "running", now),
        )
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE task_template_id = ? AND robot_id = ? ORDER BY id DESC LIMIT 1",
            (template_id, robot_id),
        )
        execution_id = execution["id"]

        for step in sorted(steps, key=lambda s: s.get("order", 0)):
            step_now = time.time()
            action = step["action"]
            params = step.get("params", {})
            result = None
            step_status = "completed"

            try:
                if action.startswith("robot."):
                    action_name = action.split(".", 1)[1]
                    path = f"/api/v1/robot/{robot_id}/{action_name}"
                    resp = await robot_proxy.forward(robot_id, path, params if params else None)
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action.startswith("sampler."):
                    action_name = action.split(".", 1)[1]
                    if action_name == "start":
                        resp = await sampler_service.start()
                    elif action_name == "stop":
                        resp = await sampler_service.stop()
                    else:
                        resp = ApiResponse(code=3002, message=f"Unknown sampler action: {action_name}")
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action == "wait_sampler_complete":
                    resp = await sampler_service.wait_complete()
                    step_status = "completed" if resp.code == 0 else "failed"
                    result = resp.model_dump()
                elif action == "delay":
                    import asyncio
                    delay_secs = params.get("seconds", 1.0)
                    await asyncio.sleep(delay_secs)
                    step_status = "completed"
                    result = {"delayed": delay_secs}
            except Exception as e:
                step_status = "failed"
                result = {"error": str(e)}

            await self._db.execute(
                "INSERT INTO task_step_logs (execution_id, step_order, action, params_json, result_json, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (execution_id, step["order"], action, json.dumps(params), json.dumps(result), step_status, step_now, time.time()),
            )

            if step_status == "failed":
                await self._db.execute(
                    "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                    ("failed", time.time(), f"Step {step['order']} ({action}) failed", execution_id),
                )
                return {"status": "failed", "execution_id": execution_id, "error_msg": f"Step {step['order']} failed"}

        await self._db.execute(
            "UPDATE task_executions SET status = ?, completed_at = ? WHERE id = ?",
            ("completed", time.time(), execution_id),
        )
        return {"status": "completed", "execution_id": execution_id}

    async def list_executions(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM task_executions ORDER BY id DESC")

    async def get_execution(self, execution_id: int) -> dict | None:
        execution = await self._db.fetch_one("SELECT * FROM task_executions WHERE id = ?", (execution_id,))
        if not execution:
            return None
        steps = await self._db.fetch_all("SELECT * FROM task_step_logs WHERE execution_id = ?", (execution_id,))
        execution["steps"] = steps
        return execution
```

- [ ] **Step 4: 运行任务引擎测试确认通过**

Run: `cd dispatch/backend && python -m pytest tests/test_task_engine.py -v`
Expected: 2 passed

- [ ] **Step 5: 实现任务管理路由**

创建 `dispatch/backend/app/api/task.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse
from app.services.task_engine import TaskEngine

router = APIRouter(prefix="/api/v1/tasks", tags=["task"])


class ExecuteRequest(BaseModel):
    template_id: str
    robot_id: str


_engine = TaskEngine()


@router.get("/templates", response_model=ApiResponse)
async def list_templates():
    templates = await _engine.list_templates()
    return ApiResponse(data=templates)


@router.post("/execute", response_model=ApiResponse)
async def execute_task(req: ExecuteRequest):
    result = await _engine.execute(req.template_id, req.robot_id, None, None)
    return ApiResponse(data=result)


@router.get("/executions", response_model=ApiResponse)
async def list_executions():
    executions = await _engine.list_executions()
    return ApiResponse(data=executions)


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution(execution_id: int):
    execution = await _engine.get_execution(execution_id)
    if not execution:
        return ApiResponse(code=3002, message="Execution not found")
    return ApiResponse(data=execution)
```

- [ ] **Step 6: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add task engine and task management API"
```

---

### Task 6: 制样机控制服务

**Files:**
- Create: `dispatch/backend/app/clients/sampler_ws.py`
- Create: `dispatch/backend/app/services/sampler_service.py`
- Create: `dispatch/backend/app/api/sampler.py`
- Create: `dispatch/backend/tests/test_sampler_api.py`

- [ ] **Step 1: 实现制样机WS客户端**

创建 `dispatch/backend/app/clients/sampler_ws.py`:

```python
import asyncio
import json
import uuid
import websockets
from furance_shared.protocol.http_schema import ApiResponse


class SamplerWsClient:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None

    async def connect(self):
        self._ws = await websockets.connect(self._ws_url)

    async def disconnect(self):
        if self._ws:
            await self._ws.close()

    async def send_command(self, command: str, params: dict | None = None) -> ApiResponse:
        if not self._ws:
            await self.connect()
        request_id = str(uuid.uuid4())
        msg = {
            "type": "command",
            "command": command,
            "params": params or {},
            "request_id": request_id,
        }
        await self._ws.send(json.dumps(msg))
        response = await asyncio.wait_for(self._ws.recv(), timeout=60.0)
        data = json.loads(response)
        return ApiResponse(
            code=0 if data.get("type") != "error" else 1,
            data=data.get("payload", {}),
        )
```

- [ ] **Step 2: 实现制样机服务**

创建 `dispatch/backend/app/services/sampler_service.py`:

```python
from furance_shared.protocol.http_schema import ApiResponse
from app.clients.sampler_ws import SamplerWsClient
from app.core.config import get_settings


class SamplerService:
    def __init__(self, ws_url: str | None = None):
        settings = get_settings()
        self._client = SamplerWsClient(ws_url or settings.sampler.ws_url)
        self._connected = False

    async def ensure_connected(self):
        if not self._connected:
            try:
                await self._client.connect()
                self._connected = True
            except Exception:
                self._connected = False

    async def start(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("start")

    async def stop(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("stop")

    async def query(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("query")

    async def wait_complete(self, poll_interval: float = 2.0, timeout: float = 600.0) -> ApiResponse:
        import asyncio
        import time
        start = time.time()
        while time.time() - start < timeout:
            resp = await self.query()
            if resp.data and resp.data.get("status") in ("completed", "error"):
                return resp
            await asyncio.sleep(poll_interval)
        return ApiResponse(code=1001, message="Sampler timeout")
```

- [ ] **Step 3: 实现制样机路由**

创建 `dispatch/backend/app/api/sampler.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse
from app.services.sampler_service import SamplerService

router = APIRouter(prefix="/api/v1/sampler", tags=["sampler"])


class SamplerCommand(BaseModel):
    command: str
    params: dict = {}


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand):
    service = SamplerService()
    if cmd.command == "start":
        return await service.start()
    elif cmd.command == "stop":
        return await service.stop()
    elif cmd.command == "query":
        return await service.query()
    return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")


@router.get("/status", response_model=ApiResponse)
async def sampler_status():
    service = SamplerService()
    return await service.query()
```

- [ ] **Step 4: 实现状态查询路由**

创建 `dispatch/backend/app/api/status.py`:

```python
from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/status", tags=["status"])

_proxy = RobotProxyService()


@router.get("/robots", response_model=ApiResponse)
async def robots_status():
    results = {}
    for robot_id in _proxy._clients:
        try:
            resp = await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")
            results[robot_id] = resp.data
        except Exception:
            results[robot_id] = {"status": "offline"}
    return ApiResponse(data=results)
```

- [ ] **Step 5: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add sampler service, API, and status routes"
```

---

### Task 7: L2监听预留

**Files:**
- Create: `dispatch/backend/app/services/l2_listener.py`
- Create: `dispatch/backend/app/clients/l2_client.py`

- [ ] **Step 1: 实现L2客户端抽象**

创建 `dispatch/backend/app/clients/l2_client.py`:

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator


class L2ClientBase(ABC):
    @abstractmethod
    async def connect(self):
        ...

    @abstractmethod
    async def disconnect(self):
        ...

    @abstractmethod
    async def listen(self) -> AsyncIterator[dict]:
        ...

    @abstractmethod
    async def send_response(self, request_id: str, result: dict):
        ...


class DefaultL2Client(L2ClientBase):
    async def connect(self):
        pass

    async def disconnect(self):
        pass

    async def listen(self) -> AsyncIterator[dict]:
        return
        yield  # make it an async generator

    async def send_response(self, request_id: str, result: dict):
        pass
```

- [ ] **Step 2: 实现L2Listener**

创建 `dispatch/backend/app/services/l2_listener.py`:

```python
import logging
from app.clients.l2_client import L2ClientBase, DefaultL2Client
from app.core.config import get_settings

logger = logging.getLogger("dispatch.l2")


class L2Listener:
    def __init__(self, client: L2ClientBase | None = None):
        settings = get_settings()
        self._enabled = settings.l2.enabled
        self._client = client or DefaultL2Client()
        self._running = False

    async def start(self):
        if not self._enabled:
            logger.info("L2 listener disabled")
            return
        self._running = True
        await self._client.connect()
        logger.info("L2 listener started")
        async for cmd in self._client.listen():
            if not self._running:
                break
            await self._on_command(cmd)

    async def stop(self):
        self._running = False
        await self._client.disconnect()
        logger.info("L2 listener stopped")

    async def _on_command(self, cmd: dict):
        logger.info(f"L2 command received: {cmd}")
        # TODO: implement when L2 protocol is defined
        # 1. Parse command → extract task_template_id + params
        # 2. Find matching template
        # 3. Call TaskEngine.execute()
        # 4. Record to l2_commands table
        # 5. Send response back via L2Client
```

- [ ] **Step 3: Commit**

```bash
git add dispatch/
git commit -m "feat(dispatch): add L2 listener and client abstraction (reserved)"
```

---

### Task 8: 全量测试验证

- [ ] **Step 1: 运行调度系统全量测试**

Run: `cd dispatch/backend && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 2: 运行shared包+控制系统测试确保无回归**

Run: `cd shared && python -m pytest tests/ -v && cd ../robot_control/backend && python -m pytest tests/ -v`
Expected: all passed

- [ ] **Step 3: 运行ruff检查**

Run: `ruff check shared/ robot_control/backend/ dispatch/backend/ && ruff format --check shared/ robot_control/backend/ dispatch/backend/`
Expected: no issues

---

## Self-Review

**1. Spec coverage:**
- 机器人控制代理 ✓ Task 4
- 导航代理 ✓ Task 4
- 任务编排引擎 ✓ Task 5
- 制样机控制 ✓ Task 6
- L2预留 ✓ Task 7
- SQLite数据持久化 ✓ Task 2
- 状态查询 ✓ Task 6
- 配置管理 ✓ Task 1

**2. Placeholder scan:** L2Listener._on_command中有TODO注释，但这是预留功能，协议未定义时无法实现，属于合理标注。

**3. Type consistency:**
- TaskEngine使用robot_proxy.forward和sampler_service方法签名与实际实现一致 ✓
- 所有API使用shared包的ApiResponse ✓
- 制样机WS电文格式与spec一致 ✓

**注意:** 前端部分和部署脚本(nssm/PyInstaller)将在集成阶段实现。
