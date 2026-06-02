# 调度系统重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构调度系统为中央协调者，负责任务编排、workflow调度执行、状态监控、报警管理和日志记录，同时新增模拟控制系统和制样机。

**Architecture:** 6个阶段顺序执行 — 共享包新增WS帧类型 → 控制系统新增异步workflow+取消+报警推送 → 调度系统后端重构 → 调度系统前端重构 → 模拟系统 → 集成测试。

**Tech Stack:** Python 3.10+ / FastAPI / Pydantic v2 / aiosqlite / Vue 3 + Element Plus / WebSocket

---

## Phase 1: 共享包新增 WS 帧类型和数据模型

### Task 1.1: 扩展 WsFrameType 枚举

**Files:**
- Modify: `shared/src/furance_shared/protocol/ws_frames.py`

- [ ] **Step 1: Add WORKFLOW_STEP and ALARM to WsFrameType**

```python
# shared/src/furance_shared/protocol/ws_frames.py
# Add WORKFLOW_STEP and ALARM to the WsFrameType enum:

class WsFrameType(StrEnum):
    STATUS = "status"
    ERROR = "error"
    LOG = "log"
    WORKFLOW_STEP = "workflow_step"
    ALARM = "alarm"
```

- [ ] **Step 2: Run existing tests to confirm no regression**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest shared/tests/test_ws_frames.py -v
```

Expected: 4 tests PASS

- [ ] **Step 3: Commit**

```bash
git add shared/src/furance_shared/protocol/ws_frames.py
git commit -m "feat: add WORKFLOW_STEP and ALARM to WsFrameType enum"
```

### Task 1.2: Add WorkflowStep and Alarm WS frame models

**Files:**
- Modify: `shared/src/furance_shared/protocol/ws_frames.py`

- [ ] **Step 1: Add new payload and frame models**

```python
# shared/src/furance_shared/protocol/ws_frames.py
# Add after the existing LogFrame class:

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
    type: WsFrameType = WsFrameType.WORKFLOW_STEP
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
    type: WsFrameType = WsFrameType.ALARM
    robot_id: str
    timestamp: Optional[int] = None
    payload: AlarmPayload
```

- [ ] **Step 2: Write tests for new frame types**

```python
# shared/tests/test_ws_frames.py
# Add at end of file:

from furance_shared.protocol.ws_frames import (
    WorkflowStepPayload, WorkflowStepFrame,
    AlarmPayload, AlarmFrame,
)


def test_workflow_step_frame():
    frame = WorkflowStepFrame(
        robot_id="robot_001",
        payload=WorkflowStepPayload(
            workflow_name="test_wf",
            execution_id="exec-001",
            step_id="step_1",
            step_index=1,
            total_steps=3,
            status="running",
            message="Moving arm",
        ),
    )
    assert frame.type == WsFrameType.WORKFLOW_STEP
    assert frame.payload.workflow_name == "test_wf"
    assert frame.payload.status == "running"


def test_workflow_step_frame_serialization():
    frame = WorkflowStepFrame(
        robot_id="robot_001",
        payload=WorkflowStepPayload(
            workflow_name="test_wf",
            execution_id="exec-001",
            step_id="step_2",
            step_index=2,
            total_steps=3,
            status="completed",
            message="Done",
        ),
    )
    data = frame.model_dump()
    assert data["type"] == "workflow_step"
    assert data["payload"]["step_index"] == 2


def test_alarm_frame():
    frame = AlarmFrame(
        robot_id="robot_001",
        payload=AlarmPayload(
            alarm_id="alarm-001",
            level="critical",
            category="arm",
            title="Arm motor overheat",
            message="Left arm J3 temperature exceeds threshold",
            source="robot_control",
        ),
    )
    assert frame.type == WsFrameType.ALARM
    assert frame.payload.level == "critical"
    assert frame.payload.category == "arm"


def test_alarm_frame_serialization():
    frame = AlarmFrame(
        robot_id="robot_001",
        payload=AlarmPayload(
            alarm_id="alarm-002",
            level="warning",
            category="battery",
            title="Low battery",
            message="Battery at 15%",
            source="robot_control",
        ),
    )
    data = frame.model_dump()
    assert data["type"] == "alarm"
    assert data["payload"]["level"] == "warning"
```

- [ ] **Step 3: Run shared tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest shared/tests/test_ws_frames.py -v
```

Expected: 8 tests PASS

- [ ] **Step 4: Commit**

```bash
git add shared/src/furance_shared/protocol/ws_frames.py shared/tests/test_ws_frames.py
git commit -m "feat: add WorkflowStepFrame and AlarmFrame WS models"
```

### Task 1.3: Update WorkflowExecuteResponse model

**Files:**
- Modify: `shared/src/furance_shared/models/workflow.py`

- [ ] **Step 1: Add execution_id and status fields**

```python
# shared/src/furance_shared/models/workflow.py
# Replace the existing WorkflowExecuteResponse with:

class WorkflowExecuteResponse(BaseModel):
    execution_id: str = ""
    status: Literal["started", "running", "completed", "failed", "cancelled"] = "started"
    success: bool = True
    message: str = ""
    step_results: list[StepResult] = []
    error_step_id: Optional[str] = None
```

- [ ] **Step 2: Run shared model tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest shared/tests/ -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add shared/src/furance_shared/models/workflow.py
git commit -m "feat: add execution_id and status to WorkflowExecuteResponse"
```

---

## Phase 2: 控制系统新增功能 (robot_control/)

### Task 2.1: Add workflow_step and alarm WS push to StatusService

**Files:**
- Modify: `robot_control/backend/app/services/status_service.py`

- [ ] **Step 1: Add push_workflow_step and push_alarm methods**

```python
# robot_control/backend/app/services/status_service.py
# Add these methods to the StatusService class:

    async def push_workflow_step(self, robot_id: str, payload: dict):
        from furance_shared.protocol.ws_frames import WorkflowStepFrame
        frame = WorkflowStepFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=payload,
        )
        await self._broadcast(frame.model_dump())

    async def push_alarm(self, robot_id: str, payload: dict):
        from furance_shared.protocol.ws_frames import AlarmFrame
        frame = AlarmFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=payload,
        )
        await self._broadcast(frame.model_dump())
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/backend/app/services/status_service.py
git commit -m "feat: add push_workflow_step and push_alarm to StatusService"
```

### Task 2.2: Refactor WorkflowService for async execution with cancellation

**Files:**
- Modify: `robot_control/backend/app/services/workflow_service.py`

- [ ] **Step 1: Rewrite WorkflowService with async execution management**

```python
# robot_control/backend/app/services/workflow_service.py
# Replace the entire file content:

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from furance_shared.models.workflow import (
    Workflow,
    WorkflowExecuteRequest,
    WorkflowExecuteResponse,
    StepResult,
    MoveStepConfig,
    UpperLimbStepConfig,
    UpperBodyStepConfig,
    GripperStepConfig,
    VisionStepConfig,
    SleepStepConfig,
)
from furance_shared.models.command import GripperCommand
from furance_shared.utils.errors import BusinessError, ErrorCode

logger = logging.getLogger(__name__)

NAV_POLL_TIMEOUT = 300
NAV_POLL_INTERVAL = 1.0


class WorkflowService:
    def __init__(
        self,
        ros2_client=None,
        moveit_client=None,
        upper_body_client=None,
        chassis_client=None,
        arm_service=None,
        arm_enable_client=None,
        workflow_dir: str = "data/workflows",
        status_service=None,
    ):
        self._ros2 = ros2_client
        self._moveit = moveit_client
        self._upper_body = upper_body_client
        self._chassis = chassis_client
        self._arm_service = arm_service
        self._arm_enable = arm_enable_client
        self._workflow_dir = Path(workflow_dir)
        self._status_service = status_service
        self._active_executions: dict[str, asyncio.Event] = {}

    # -- CRUD (unchanged) --

    def _robot_dir(self, robot_id: str) -> Path:
        return self._workflow_dir / robot_id

    def _file_path(self, robot_id: str, name: str) -> Path:
        return self._robot_dir(robot_id) / f"{name}.json"

    def list_workflows(self, robot_id: str) -> list[dict]:
        robot_dir = self._robot_dir(robot_id)
        if not robot_dir.is_dir():
            return []
        result = []
        for f in sorted(robot_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                result.append({
                    "name": data.get("name", f.stem),
                    "description": data.get("description", ""),
                    "step_count": len(data.get("steps", [])),
                    "version": data.get("version", 1),
                })
            except Exception:
                result.append({
                    "name": f.stem,
                    "description": "",
                    "step_count": 0,
                    "version": 1,
                })
        return result

    def get_workflow(self, robot_id: str, name: str) -> Workflow:
        file_path = self._file_path(robot_id, name)
        if not file_path.exists():
            raise BusinessError(
                message=f"Workflow '{name}' not found",
                code=ErrorCode.WORKFLOW_NOT_FOUND,
            )
        return Workflow(**json.loads(file_path.read_text()))

    def save_workflow(self, robot_id: str, workflow: Workflow, overwrite: bool = False) -> None:
        robot_dir = self._robot_dir(robot_id)
        robot_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._file_path(robot_id, workflow.name)
        if file_path.exists() and not overwrite:
            raise BusinessError(
                message=f"Workflow '{workflow.name}' already exists",
                code=ErrorCode.WORKFLOW_NAME_EXISTS,
            )
        file_path.write_text(json.dumps(workflow.model_dump(), indent=2, ensure_ascii=False))

    def delete_workflow(self, robot_id: str, name: str) -> None:
        file_path = self._file_path(robot_id, name)
        if file_path.exists():
            file_path.unlink()

    # -- Async execution engine --

    async def start_execution(
        self, robot_id: str, name: str, execute_req: WorkflowExecuteRequest
    ) -> str:
        workflow = self.get_workflow(robot_id, name)
        execution_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event

        asyncio.create_task(self._run_workflow(execution_id, robot_id, workflow, execute_req, cancel_event))
        return execution_id

    async def _run_workflow(
        self, execution_id: str, robot_id: str, workflow: Workflow,
        execute_req: WorkflowExecuteRequest, cancel_event: asyncio.Event,
    ):
        nav_lookup = {np.step_id: np for np in execute_req.nav_params}
        context: dict[str, dict] = {}
        step_results: list[StepResult] = []

        try:
            for i, step in enumerate(workflow.steps):
                if cancel_event.is_set():
                    await self._push_step(robot_id, execution_id, workflow.name, step, i, len(workflow.steps), "cancelled", "Cancelled by user")
                    break

                await self._push_step(robot_id, execution_id, workflow.name, step, i, len(workflow.steps), "running", f"Executing: {step.label}")

                try:
                    result = await self._dispatch_step(step, nav_lookup, context, robot_id)
                    step_results.append(result)
                    if not result.success:
                        await self._push_step(robot_id, execution_id, workflow.name, step, i, len(workflow.steps), "failed", result.message)
                        break
                    await self._push_step(robot_id, execution_id, workflow.name, step, i, len(workflow.steps), "completed", result.message, result.data)
                except Exception as exc:
                    logger.exception("Workflow step '%s' error", step.label)
                    step_results.append(StepResult(step_id=step.id, success=False, message=str(exc)))
                    await self._push_step(robot_id, execution_id, workflow.name, step, i, len(workflow.steps), "failed", str(exc))
                    break
        finally:
            self._active_executions.pop(execution_id, None)

    async def cancel_workflow(self, robot_id: str, name: str) -> bool:
        cancelled_any = False
        for exec_id, event in list(self._active_executions.items()):
            event.set()
            cancelled_any = True

        if self._chassis is not None:
            try:
                await self._chassis.stop_task()
            except Exception as e:
                logger.warning("Failed to stop chassis navigation: %s", e)

        if self._arm_enable is not None:
            try:
                await self._arm_enable.enable(False)
                await self._arm_enable.clear_error()
            except Exception as e:
                logger.warning("Failed to disable arm: %s", e)

        return cancelled_any

    def get_execution_status(self, execution_id: str) -> dict | None:
        if execution_id in self._active_executions:
            return {"execution_id": execution_id, "status": "running"}
        return None

    async def _push_step(self, robot_id, execution_id, workflow_name, step, idx, total, status, message, data=None):
        if self._status_service is None:
            return
        await self._status_service.push_workflow_step(robot_id, {
            "workflow_name": workflow_name,
            "execution_id": execution_id,
            "step_id": step.id,
            "step_index": idx + 1,
            "total_steps": total,
            "status": status,
            "message": message,
            "data": data or {},
        })

    # -- Step dispatch (unchanged from original) --

    async def _dispatch_step(self, step, nav_lookup, context, robot_id) -> StepResult:
        handlers = {
            "move": self._execute_move,
            "upper_limb": self._execute_upper_limb,
            "upper_body": self._execute_upper_body,
            "gripper": self._execute_gripper,
            "vision": self._execute_vision,
            "sleep": self._execute_sleep,
        }
        handler = handlers.get(step.type)
        if handler is None:
            return StepResult(step_id=step.id, success=False, message=f"Unknown step type: {step.type}")
        return await handler(step, nav_lookup, context, robot_id)

    async def _execute_move(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._chassis is None:
            return StepResult(step_id=step.id, success=False, message="Chassis client not available")
        nav = nav_lookup.get(step.id)
        if nav is None:
            return StepResult(step_id=step.id, success=False, message="Navigation params not provided for this step")
        config = MoveStepConfig(**step.config)
        task_body = {
            "map_name": nav.map_name,
            "loop": False,
            "tasks": [{
                "name": nav.path_type,
                "start_param": {
                    "map_name": nav.map_name,
                    "position_name": nav.point_name or "",
                    "path_name": nav.path_name or "",
                },
            }],
        }
        start_res = await self._chassis.start_task(task_body)
        if not start_res.get("successed", start_res.get("success", False)):
            return StepResult(step_id=step.id, success=False, message=start_res.get("msg", "Navigation start failed"))
        for _ in range(NAV_POLL_TIMEOUT):
            await asyncio.sleep(NAV_POLL_INTERVAL)
            try:
                status = await self._chassis.is_task_finished()
                if status.get("data", {}).get("is_finished", False):
                    return StepResult(step_id=step.id, success=True, message="Navigation completed")
            except Exception:
                pass
        return StepResult(step_id=step.id, success=False, message="Navigation timed out")

    async def _execute_upper_limb(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._moveit is None:
            return StepResult(step_id=step.id, success=False, message="MoveIt client not available")
        config = UpperLimbStepConfig(**step.config)
        if config.mode == "preset":
            if not config.preset_name or self._arm_service is None:
                return StepResult(step_id=step.id, success=False, message="Preset name required")
            presets = self._arm_service.list_teach(robot_id)
            preset = next((p for p in presets if p.name == config.preset_name and p.arm.value == config.arm), None)
            if preset is None:
                return StepResult(step_id=step.id, success=False, message=f"Preset '{config.preset_name}' not found")
            method = config.method
            if method == "moveJ":
                result = await self._moveit.move_j(config.arm, preset.joint_angles)
            elif method == "moveL":
                result = await self._moveit.move_l(config.arm, [preset.end_effector.model_dump()])
            else:
                to_frame = f"ARM-{'L' if config.arm == 'left' else 'R'}-J7_Link"
                result = await self._moveit.move_p(
                    config.arm, preset.end_effector.model_dump(),
                    to_frame, preset.coordinate_frame, "ompl",
                )
        else:
            resolved = self._resolve_variables(config.position or {}, context)
            to_frame = f"ARM-{'L' if config.arm == 'left' else 'R'}-J7_Link"
            result = await self._moveit.move_p(
                config.arm, resolved,
                to_frame, config.reference_frame or "base_link", "ompl",
            )
        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Upper limb move failed"))
        return StepResult(step_id=step.id, success=True, message="Upper limb move completed")

    async def _execute_upper_body(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._upper_body is None:
            return StepResult(step_id=step.id, success=False, message="Upper body client not available")
        config = UpperBodyStepConfig(**step.config)
        if config.waist_angle is not None:
            r = await self._upper_body.waist_control(config.waist_angle, config.waist_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Waist control failed"))
        if config.ascend_pos is not None:
            r = await self._upper_body.ascend_control(config.ascend_pos, config.ascend_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Ascend control failed"))
        if config.head_angle is not None:
            r = await self._upper_body.head_control(config.head_angle, config.head_speed)
            if r.get("success") is False:
                return StepResult(step_id=step.id, success=False, message=r.get("message", "Head control failed"))
        return StepResult(step_id=step.id, success=True, message="Upper body control completed")

    async def _execute_gripper(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._ros2 is None:
            return StepResult(step_id=step.id, success=False, message="ROS2 client not available")
        config = GripperStepConfig(**step.config)
        cmd = GripperCommand(arm=config.arm, action=config.action, force=config.force)
        result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Gripper command failed"))
        return StepResult(step_id=step.id, success=True, message=f"Gripper {config.action} completed")

    async def _execute_vision(self, step, nav_lookup, context, robot_id) -> StepResult:
        if self._ros2 is None:
            return StepResult(step_id=step.id, success=False, message="ROS2 client not available")
        config = VisionStepConfig(**step.config)
        result = await self._ros2.call_service("/vision_detect", {"scene": config.scene, "camera_id": config.camera_id})
        if result.get("success") is False:
            return StepResult(step_id=step.id, success=False, message=result.get("message", "Vision detection failed"))
        data = result.get("data", {})
        grasp_pose = data.get("grasp_pose") or data
        context[step.id] = {"grasp_pose": grasp_pose}
        return StepResult(step_id=step.id, success=True, message="Vision detection completed", data={"grasp_pose": grasp_pose})

    async def _execute_sleep(self, step, nav_lookup, context, robot_id) -> StepResult:
        config = SleepStepConfig(**step.config)
        await asyncio.sleep(config.duration)
        return StepResult(step_id=step.id, success=True, message=f"Slept {config.duration}s")

    @staticmethod
    def _resolve_variables(value: Any, context: dict) -> Any:
        if isinstance(value, str) and value.startswith("$"):
            parts = value[1:].split(".")
            current: Any = context
            for key in parts:
                if isinstance(current, dict):
                    current = current.get(key)
                else:
                    return value
            return current
        elif isinstance(value, dict):
            return {k: WorkflowService._resolve_variables(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [WorkflowService._resolve_variables(v, context) for v in value]
        return value
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/backend/app/services/workflow_service.py
git commit -m "feat: refactor WorkflowService for async execution with cancellation"
```

### Task 2.3: Update workflow API for async execution and cancellation

**Files:**
- Modify: `robot_control/backend/app/api/workflow.py`

- [ ] **Step 1: Rewrite workflow API**

```python
# robot_control/backend/app/api/workflow.py
# Replace the entire file content:

from fastapi import APIRouter, HTTPException, Request
from furance_shared.models.workflow import Workflow, WorkflowExecuteRequest
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.workflow_service import WorkflowService
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/robot/{robot_id}/workflows", tags=["workflows"])


def _get_workflow_service(request: Request) -> WorkflowService:
    settings = get_settings()
    ros2 = request.app.state.ros2
    from app.services.arm_service import ArmService
    arm_service = ArmService(
        ros2_client=ros2.service_client,
        moveit_client=ros2.moveit_client,
        teach_dir=settings.teach_data_dir,
    )
    return WorkflowService(
        ros2_client=ros2.service_client,
        moveit_client=ros2.moveit_client,
        upper_body_client=ros2.upper_body_client,
        chassis_client=request.app.state.chassis_client,
        arm_service=arm_service,
        arm_enable_client=ros2.arm_enable_client,
        workflow_dir=settings.workflow_data_dir,
        status_service=request.app.state.status_service,
    )


@router.get("", response_model=ApiResponse)
async def list_workflows(robot_id: str, request: Request):
    workflows = _get_workflow_service(request).list_workflows(robot_id)
    return ApiResponse(data=workflows)


@router.get("/{name}", response_model=ApiResponse)
async def get_workflow(robot_id: str, name: str, request: Request):
    try:
        wf = _get_workflow_service(request).get_workflow(robot_id, name)
        return ApiResponse(data=wf.model_dump())
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.post("/{name}", response_model=ApiResponse)
async def create_workflow(robot_id: str, name: str, workflow: Workflow, request: Request):
    if workflow.name and workflow.name != name:
        raise HTTPException(status_code=400, detail={"code": 3002, "message": "Workflow name mismatch"})
    workflow.name = name
    try:
        _get_workflow_service(request).save_workflow(robot_id, workflow)
        return ApiResponse(data={"name": name})
    except FuranceError as e:
        raise HTTPException(status_code=409, detail=e.to_dict())


@router.put("/{name}", response_model=ApiResponse)
async def update_workflow(robot_id: str, name: str, workflow: Workflow, request: Request):
    if workflow.name and workflow.name != name:
        raise HTTPException(status_code=400, detail={"code": 3002, "message": "Workflow name mismatch"})
    workflow.name = name
    try:
        _get_workflow_service(request).save_workflow(robot_id, workflow, overwrite=True)
        return ApiResponse(data={"name": name})
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.delete("/{name}", response_model=ApiResponse)
async def delete_workflow(robot_id: str, name: str, request: Request):
    _get_workflow_service(request).delete_workflow(robot_id, name)
    return ApiResponse(data={"deleted": name})


@router.post("/{name}/execute", response_model=ApiResponse)
async def execute_workflow(robot_id: str, name: str, req: WorkflowExecuteRequest, request: Request):
    try:
        service = _get_workflow_service(request)
        execution_id = await service.start_execution(robot_id, name, req)
        return ApiResponse(data={"execution_id": execution_id, "status": "started"})
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.post("/{name}/cancel", response_model=ApiResponse)
async def cancel_workflow(robot_id: str, name: str, request: Request):
    service = _get_workflow_service(request)
    cancelled = await service.cancel_workflow(robot_id, name)
    return ApiResponse(data={"cancelled": cancelled})


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution_status(robot_id: str, execution_id: str, request: Request):
    service = _get_workflow_service(request)
    status = service.get_execution_status(execution_id)
    if status is None:
        return ApiResponse(code=3002, message="Execution not found", data=None)
    return ApiResponse(data=status)
```

- [ ] **Step 2: Commit**

```bash
git add robot_control/backend/app/api/workflow.py
git commit -m "feat: add async workflow execution, cancel, and status APIs"
```

### Task 2.4: Run control system tests

**Files:**
- Test: `robot_control/backend/tests/`

- [ ] **Step 1: Run existing control system tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest robot_control/backend/tests/ -v --ignore=robot_control/backend/tests/test_moveit_client.py --ignore=robot_control/backend/tests/test_ros2_factory.py --ignore=robot_control/backend/tests/test_ros2_nodes_api.py
```

Expected: All non-ROS2 tests PASS

- [ ] **Step 2: Commit if any test file needed updates**

(No commit needed if tests pass)

---

## Phase 3: 调度系统后端重构 (dispatch/)

### Task 3.1: Create dispatch data models

**Files:**
- Create: `dispatch/backend/app/models/task.py`
- Create: `dispatch/backend/app/models/alarm.py`

- [ ] **Step 1: Create task models**

```python
# dispatch/backend/app/models/task.py

from pydantic import BaseModel, Field
from furance_shared.utils.enum import StrEnum
from typing import Literal, Optional


class TaskStepType(StrEnum):
    WORKFLOW = "workflow"
    SAMPLER = "sampler"
    DELAY = "delay"


class WorkflowStepConfig(BaseModel):
    robot_id: str
    workflow_name: str


class SamplerStepConfig(BaseModel):
    command: str
    params: dict = {}


class DelayStepConfig(BaseModel):
    seconds: float = Field(gt=0, default=1.0)


class TaskStep(BaseModel):
    id: str = Field(min_length=1)
    type: TaskStepType
    label: str = ""
    config: dict = {}


class TaskTemplate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    steps: list[TaskStep] = []
    version: int = 1
```

- [ ] **Step 2: Create alarm models**

```python
# dispatch/backend/app/models/alarm.py

from pydantic import BaseModel, Field
from furance_shared.utils.enum import StrEnum


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


class AlarmRuleCondition(BaseModel):
    field: str
    operator: str = "<"   # <, >, <=, >=, ==, !=
    value: float


class AlarmRule(BaseModel):
    id: Optional[int] = None
    name: str
    category: str
    level: AlarmLevel
    condition_json: dict
    enabled: bool = True
```

- [ ] **Step 3: Commit**

```bash
git add dispatch/backend/app/models/task.py dispatch/backend/app/models/alarm.py
git commit -m "feat: add dispatch task and alarm data models"
```

### Task 3.2: Update database schema

**Files:**
- Modify: `dispatch/backend/app/core/database.py`

- [ ] **Step 1: Rewrite SCHEMA with new tables**

```python
# dispatch/backend/app/core/database.py
# Replace the SCHEMA constant:

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
    description TEXT DEFAULT '',
    steps_json TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_template_id TEXT NOT NULL,
    trigger_type TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'pending',
    started_at REAL,
    completed_at REAL,
    error_msg TEXT,
    current_step_id TEXT
);

CREATE TABLE IF NOT EXISTS execution_step_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    step_order INTEGER NOT NULL,
    step_id TEXT NOT NULL,
    step_type TEXT NOT NULL,
    step_config_json TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    sub_step_results_json TEXT,
    started_at REAL,
    completed_at REAL,
    error_msg TEXT
);

CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    robot_id TEXT DEFAULT '',
    source TEXT DEFAULT '',
    level TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    ack_status TEXT DEFAULT 'unack',
    ack_by TEXT DEFAULT '',
    ack_at REAL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alarm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    level TEXT NOT NULL,
    condition_json TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS operation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    robot_id TEXT DEFAULT '',
    level TEXT NOT NULL,
    node TEXT DEFAULT '',
    message TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS robot_status (
    robot_id TEXT PRIMARY KEY,
    status_json TEXT DEFAULT '{}',
    updated_at REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sampler_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT DEFAULT 'idle',
    progress INTEGER DEFAULT 0,
    status_json TEXT DEFAULT '{}',
    last_update REAL NOT NULL
);
"""
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/core/database.py
git commit -m "feat: update dispatch database schema for new modules"
```

### Task 3.3: Create TaskEditor service

**Files:**
- Create: `dispatch/backend/app/services/task_editor.py`

- [ ] **Step 1: Write TaskEditor service**

```python
# dispatch/backend/app/services/task_editor.py

import json
import time
from app.core.database import Database
from app.models.task import TaskTemplate, TaskStep


class TaskEditor:
    def __init__(self, db: Database):
        self._db = db

    async def create(self, template: TaskTemplate) -> dict:
        now = time.time()
        steps_json = json.dumps([s.model_dump() for s in template.steps], ensure_ascii=False)
        await self._db.execute(
            "INSERT INTO task_templates (id, name, description, steps_json, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template.id, template.name, template.description, steps_json, template.version, now, now),
        )
        return {"id": template.id, "name": template.name}

    async def list_all(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM task_templates ORDER BY updated_at DESC")

    async def get(self, template_id: str) -> dict | None:
        return await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))

    async def update(self, template: TaskTemplate) -> dict | None:
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template.id,))
        if not existing:
            return None
        now = time.time()
        steps_json = json.dumps([s.model_dump() for s in template.steps], ensure_ascii=False)
        await self._db.execute(
            "UPDATE task_templates SET name = ?, description = ?, steps_json = ?, version = ?, updated_at = ? WHERE id = ?",
            (template.name, template.description, steps_json, template.version, now, template.id),
        )
        return {"id": template.id, "name": template.name}

    async def delete(self, template_id: str) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM task_templates WHERE id = ?", (template_id,))
        if not existing:
            return False
        await self._db.execute("DELETE FROM task_templates WHERE id = ?", (template_id,))
        return True
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/services/task_editor.py
git commit -m "feat: add TaskEditor service for task template CRUD"
```

### Task 3.4: Create TaskExecutor service

**Files:**
- Create: `dispatch/backend/app/services/task_executor.py`

- [ ] **Step 1: Write TaskExecutor service**

```python
# dispatch/backend/app/services/task_executor.py

import asyncio
import json
import logging
import time
import uuid
from app.core.database import Database
from app.models.task import TaskStepType, DelayStepConfig

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(self, db: Database, robot_proxy, sampler_service, ws_manager=None):
        self._db = db
        self._robot_proxy = robot_proxy
        self._sampler = sampler_service
        self._ws_manager = ws_manager
        self._active_executions: dict[int, asyncio.Event] = {}
        self._critical_alarm_received = asyncio.Event()

    def notify_critical_alarm(self):
        self._critical_alarm_received.set()

    async def execute(self, template_id: str, trigger_type: str = "manual") -> dict:
        template = await self._db.fetch_one("SELECT * FROM task_templates WHERE id = ?", (template_id,))
        if not template:
            return {"status": "error", "error_msg": f"Template {template_id} not found"}

        steps = json.loads(template["steps_json"])
        now = time.time()

        await self._db.execute(
            "INSERT INTO task_executions (task_template_id, trigger_type, status, started_at) VALUES (?, ?, ?, ?)",
            (template_id, trigger_type, "running", now),
        )
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE task_template_id = ? ORDER BY id DESC LIMIT 1",
            (template_id,),
        )
        execution_id = execution["id"]
        cancel_event = asyncio.Event()
        self._active_executions[execution_id] = cancel_event
        self._critical_alarm_received.clear()

        try:
            for i, step in enumerate(steps):
                if cancel_event.is_set():
                    await self._update_execution(execution_id, "cancelled", error_msg="Cancelled by user")
                    return {"status": "cancelled", "execution_id": execution_id}

                if self._critical_alarm_received.is_set():
                    await self._update_execution(execution_id, "failed", error_msg="Critical alarm triggered")
                    return {"status": "failed", "execution_id": execution_id}

                step_now = time.time()
                await self._db.execute(
                    "INSERT INTO execution_step_logs (execution_id, step_order, step_id, step_type, step_config_json, status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (execution_id, i + 1, step["id"], step["type"], json.dumps(step.get("config", {})), "running", step_now),
                )

                step_log = await self._db.fetch_one(
                    "SELECT id FROM execution_step_logs WHERE execution_id = ? AND step_order = ?",
                    (execution_id, i + 1),
                )
                step_log_id = step_log["id"]

                try:
                    if step["type"] == TaskStepType.WORKFLOW:
                        await self._execute_workflow_step(step, execution_id, step_log_id, cancel_event)
                    elif step["type"] == TaskStepType.SAMPLER:
                        await self._execute_sampler_step(step, execution_id, step_log_id, cancel_event)
                    elif step["type"] == TaskStepType.DELAY:
                        await self._execute_delay_step(step, execution_id, step_log_id, cancel_event)
                except Exception as e:
                    logger.exception("Step %s failed", step.get("label", step["id"]))
                    await self._db.execute(
                        "UPDATE execution_step_logs SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                        ("failed", time.time(), str(e), step_log_id),
                    )
                    await self._update_execution(execution_id, "failed", error_msg=f"Step '{step.get('label', step['id'])}' failed: {e}")
                    return {"status": "failed", "execution_id": execution_id}

                await self._db.execute(
                    "UPDATE execution_step_logs SET status = ?, completed_at = ? WHERE id = ?",
                    ("completed", time.time(), step_log_id),
                )

            await self._update_execution(execution_id, "completed")
            return {"status": "completed", "execution_id": execution_id}
        finally:
            self._active_executions.pop(execution_id, None)

    async def _execute_workflow_step(self, step, execution_id, step_log_id, cancel_event):
        config = step.get("config", {})
        robot_id = config.get("robot_id", "robot_001")
        workflow_name = config.get("workflow_name", "")

        resp = await self._robot_proxy.forward(
            robot_id,
            f"/api/v1/robot/{robot_id}/workflows/{workflow_name}/execute",
            {"nav_params": []},
        )
        if resp.code != 0:
            raise Exception(f"Failed to start workflow: {resp.message}")

        wf_execution_id = resp.data.get("execution_id", "")
        sub_results = []

        # Poll for workflow completion
        while True:
            if cancel_event.is_set():
                await self._robot_proxy.forward(
                    robot_id,
                    f"/api/v1/robot/{robot_id}/workflows/{workflow_name}/cancel",
                )
                raise Exception("Workflow cancelled")

            status_resp = await self._robot_proxy.forward_get(
                robot_id,
                f"/api/v1/robot/{robot_id}/workflows/executions/{wf_execution_id}",
            )
            if status_resp.code != 0:
                break  # execution not found = finished

            await asyncio.sleep(1.0)

        await self._db.execute(
            "UPDATE execution_step_logs SET sub_step_results_json = ? WHERE id = ?",
            (json.dumps(sub_results), step_log_id),
        )

    async def _execute_sampler_step(self, step, execution_id, step_log_id, cancel_event):
        config = step.get("config", {})
        command = config.get("command", "")

        if command == "start":
            resp = await self._sampler.start()
        elif command == "stop":
            resp = await self._sampler.stop()
        else:
            raise Exception(f"Unknown sampler command: {command}")

        if resp.code != 0:
            raise Exception(f"Sampler command failed: {resp.message}")

    async def _execute_delay_step(self, step, execution_id, step_log_id, cancel_event):
        config = DelayStepConfig(**step.get("config", {}))
        for _ in range(int(config.seconds)):
            if cancel_event.is_set():
                raise Exception("Delay cancelled")
            await asyncio.sleep(1.0)

    async def _update_execution(self, execution_id, status, error_msg=None):
        now = time.time()
        if error_msg:
            await self._db.execute(
                "UPDATE task_executions SET status = ?, completed_at = ?, error_msg = ? WHERE id = ?",
                (status, now, error_msg, execution_id),
            )
        else:
            await self._db.execute(
                "UPDATE task_executions SET status = ?, completed_at = ? WHERE id = ?",
                (status, now, execution_id),
            )

    async def cancel(self, execution_id: int) -> bool:
        event = self._active_executions.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    async def list_executions(self, limit: int = 50) -> list[dict]:
        return await self._db.fetch_all(
            "SELECT * FROM task_executions ORDER BY id DESC LIMIT ?", (limit,)
        )

    async def get_execution(self, execution_id: int) -> dict | None:
        execution = await self._db.fetch_one(
            "SELECT * FROM task_executions WHERE id = ?", (execution_id,)
        )
        if not execution:
            return None
        steps = await self._db.fetch_all(
            "SELECT * FROM execution_step_logs WHERE execution_id = ? ORDER BY step_order",
            (execution_id,),
        )
        execution["steps"] = steps
        return execution
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/services/task_executor.py
git commit -m "feat: add TaskExecutor service for task execution engine"
```

### Task 3.5: Create AlarmService

**Files:**
- Create: `dispatch/backend/app/services/alarm_service.py`

- [ ] **Step 1: Write AlarmService**

```python
# dispatch/backend/app/services/alarm_service.py

import json
import time
import uuid
import logging
from app.core.database import Database
from app.models.alarm import AlarmLevel, AlarmRule

logger = logging.getLogger(__name__)


class AlarmService:
    def __init__(self, db: Database, task_executor=None):
        self._db = db
        self._task_executor = task_executor

    async def create_alarm(self, robot_id: str, source: str, level: str, category: str,
                           title: str, message: str) -> dict:
        alarm_id = str(uuid.uuid4())
        now = time.time()
        await self._db.execute(
            "INSERT INTO alarms (id, robot_id, source, level, category, title, message, ack_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (alarm_id, robot_id, source, level, category, title, message, "unack", now),
        )
        if level == AlarmLevel.CRITICAL and self._task_executor:
            self._task_executor.notify_critical_alarm()
        return {
            "id": alarm_id, "robot_id": robot_id, "source": source,
            "level": level, "category": category, "title": title, "message": message,
        }

    async def list_alarms(self, level: str = None, robot_id: str = None,
                          ack_status: str = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM alarms WHERE 1=1"
        params = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if robot_id:
            query += " AND robot_id = ?"
            params.append(robot_id)
        if ack_status:
            query += " AND ack_status = ?"
            params.append(ack_status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._db.fetch_all(query, tuple(params))

    async def ack_alarm(self, alarm_id: str, ack_by: str = "operator") -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarms WHERE id = ?", (alarm_id,))
        if not existing:
            return False
        now = time.time()
        await self._db.execute(
            "UPDATE alarms SET ack_status = ?, ack_by = ?, ack_at = ? WHERE id = ?",
            ("acked", ack_by, now, alarm_id),
        )
        return True

    async def check_conditions(self, status_data: dict) -> list[dict]:
        rules = await self._db.fetch_all("SELECT * FROM alarm_rules WHERE enabled = 1")
        triggered = []
        for rule in rules:
            condition = json.loads(rule["condition_json"])
            field = condition.get("field", "")
            operator = condition.get("operator", "<")
            threshold = condition.get("value", 0)
            current = self._get_nested_value(status_data, field)
            if current is None:
                continue
            if self._evaluate(current, operator, threshold):
                alarm = await self.create_alarm(
                    robot_id=status_data.get("robot_id", ""),
                    source="robot",
                    level=rule["level"],
                    category=rule["category"],
                    title=rule["name"],
                    message=f"{field} = {current}, threshold {operator} {threshold}",
                )
                triggered.append(alarm)
        return triggered

    async def list_rules(self) -> list[dict]:
        return await self._db.fetch_all("SELECT * FROM alarm_rules ORDER BY id")

    async def create_rule(self, rule: AlarmRule) -> dict:
        now = time.time()
        await self._db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (rule.name, rule.category, rule.level, json.dumps(rule.condition_json), int(rule.enabled), now),
        )
        rows = await self._db.fetch_all("SELECT last_insert_rowid() as id")
        return {"id": rows[0]["id"], "name": rule.name}

    async def update_rule(self, rule_id: int, rule: AlarmRule) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarm_rules WHERE id = ?", (rule_id,))
        if not existing:
            return False
        await self._db.execute(
            "UPDATE alarm_rules SET name = ?, category = ?, level = ?, condition_json = ?, enabled = ? WHERE id = ?",
            (rule.name, rule.category, rule.level, json.dumps(rule.condition_json), int(rule.enabled), rule_id),
        )
        return True

    async def delete_rule(self, rule_id: int) -> bool:
        existing = await self._db.fetch_one("SELECT id FROM alarm_rules WHERE id = ?", (rule_id,))
        if not existing:
            return False
        await self._db.execute("DELETE FROM alarm_rules WHERE id = ?", (rule_id,))
        return True

    @staticmethod
    def _get_nested_value(data: dict, field: str):
        parts = field.split(".")
        current = data
        for p in parts:
            if isinstance(current, dict):
                current = current.get(p)
            else:
                return None
        return current

    @staticmethod
    def _evaluate(current, operator: str, threshold) -> bool:
        ops = {
            "<": lambda a, b: a < b,
            ">": lambda a, b: a > b,
            "<=": lambda a, b: a <= b,
            ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        fn = ops.get(operator)
        if fn is None:
            return False
        try:
            return fn(float(current), float(threshold))
        except (ValueError, TypeError):
            return fn(str(current), str(threshold))
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/services/alarm_service.py
git commit -m "feat: add AlarmService with rule engine and ack workflow"
```

### Task 3.6: Create StatusMonitor service

**Files:**
- Create: `dispatch/backend/app/services/status_monitor.py`
- Create: `dispatch/backend/app/clients/robot_ws.py`

- [ ] **Step 1: Create Robot WS client**

```python
# dispatch/backend/app/clients/robot_ws.py

import asyncio
import json
import logging
import websockets

logger = logging.getLogger(__name__)


class RobotWsClient:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._running = False
        self._handlers: dict[str, list] = {}

    def on(self, frame_type: str, handler):
        if frame_type not in self._handlers:
            self._handlers[frame_type] = []
        self._handlers[frame_type].append(handler)

    async def connect(self):
        self._running = True
        while self._running:
            try:
                self._ws = await websockets.connect(self._ws_url)
                logger.info("Connected to robot WS: %s", self._ws_url)
                async for raw in self._ws:
                    try:
                        frame = json.loads(raw)
                        frame_type = frame.get("type", "")
                        for handler in self._handlers.get(frame_type, []):
                            await handler(frame)
                        for handler in self._handlers.get("*", []):
                            await handler(frame)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.warning("Robot WS disconnected: %s, retrying in 5s", e)
                await asyncio.sleep(5.0)

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
```

- [ ] **Step 2: Create StatusMonitor service**

```python
# dispatch/backend/app/services/status_monitor.py

import json
import logging
import time
from app.core.database import Database
from app.clients.robot_ws import RobotWsClient

logger = logging.getLogger(__name__)


class StatusMonitor:
    def __init__(self, db: Database, alarm_service=None, ws_broadcast=None):
        self._db = db
        self._alarm_service = alarm_service
        self._ws_broadcast = ws_broadcast
        self._clients: dict[str, RobotWsClient] = {}
        self._robot_configs: dict[str, dict] = {}

    async def register_robot(self, robot_id: str, ws_url: str):
        self._robot_configs[robot_id] = {"ws_url": ws_url}
        client = RobotWsClient(ws_url)
        client.on("status", lambda frame, rid=robot_id: self._on_status(rid, frame))
        client.on("log", lambda frame, rid=robot_id: self._on_log(rid, frame))
        client.on("alarm", lambda frame, rid=robot_id: self._on_alarm(rid, frame))
        client.on("workflow_step", lambda frame, rid=robot_id: self._on_workflow_step(rid, frame))
        self._clients[robot_id] = client
        asyncio.ensure_future(client.connect())

    async def _on_status(self, robot_id: str, frame: dict):
        now = time.time()
        payload = frame.get("payload", {})
        await self._db.execute(
            "INSERT OR REPLACE INTO robot_status (robot_id, status_json, updated_at) VALUES (?, ?, ?)",
            (robot_id, json.dumps(payload), now),
        )
        if self._alarm_service:
            payload["robot_id"] = robot_id
            await self._alarm_service.check_conditions(payload)
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_log(self, robot_id: str, frame: dict):
        now = time.time()
        payload = frame.get("payload", {})
        await self._db.execute(
            "INSERT INTO operation_logs (source, robot_id, level, node, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("robot_control", robot_id, payload.get("level", "info"),
             payload.get("node", ""), payload.get("message", ""), now),
        )
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_alarm(self, robot_id: str, frame: dict):
        payload = frame.get("payload", {})
        if self._alarm_service:
            await self._alarm_service.create_alarm(
                robot_id=robot_id,
                source="robot",
                level=payload.get("level", "warning"),
                category=payload.get("category", "system"),
                title=payload.get("title", ""),
                message=payload.get("message", ""),
            )
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_workflow_step(self, robot_id: str, frame: dict):
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def get_robot_status(self, robot_id: str) -> dict | None:
        row = await self._db.fetch_one(
            "SELECT * FROM robot_status WHERE robot_id = ?", (robot_id,)
        )
        if not row:
            return None
        return {
            "robot_id": row["robot_id"],
            "status": json.loads(row["status_json"]),
            "updated_at": row["updated_at"],
        }

    async def get_all_robot_status(self) -> list[dict]:
        robots = await self._db.fetch_all("SELECT * FROM robots")
        result = []
        for robot in robots:
            status_row = await self._db.fetch_one(
                "SELECT * FROM robot_status WHERE robot_id = ?", (robot["id"],)
            )
            robot["status_data"] = json.loads(status_row["status_json"]) if status_row else None
            result.append(robot)
        return result

    async def stop(self):
        for client in self._clients.values():
            await client.disconnect()
```

- [ ] **Step 3: Commit**

```bash
git add dispatch/backend/app/clients/robot_ws.py dispatch/backend/app/services/status_monitor.py
git commit -m "feat: add StatusMonitor service and RobotWsClient"
```

### Task 3.7: Create LogService for dispatch

**Files:**
- Create: `dispatch/backend/app/services/log_service.py`

- [ ] **Step 1: Write LogService**

```python
# dispatch/backend/app/services/log_service.py

from app.core.database import Database


class LogService:
    def __init__(self, db: Database):
        self._db = db

    async def list_logs(self, level: str = None, source: str = None,
                        robot_id: str = None, limit: int = 200) -> list[dict]:
        query = "SELECT * FROM operation_logs WHERE 1=1"
        params = []
        if level:
            query += " AND level = ?"
            params.append(level)
        if source:
            query += " AND source = ?"
            params.append(source)
        if robot_id:
            query += " AND robot_id = ?"
            params.append(robot_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return await self._db.fetch_all(query, tuple(params))

    async def add_log(self, source: str, level: str, message: str,
                      robot_id: str = "", node: str = ""):
        import time
        now = time.time()
        await self._db.execute(
            "INSERT INTO operation_logs (source, robot_id, level, node, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source, robot_id, level, node, message, now),
        )
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/services/log_service.py
git commit -m "feat: add LogService for operation log queries"
```

### Task 3.8: Create dispatch API routes

**Files:**
- Create: `dispatch/backend/app/api/robots.py`
- Create: `dispatch/backend/app/api/executions.py`
- Create: `dispatch/backend/app/api/alarms.py`
- Create: `dispatch/backend/app/api/logs.py`
- Modify: `dispatch/backend/app/api/task.py`
- Modify: `dispatch/backend/app/api/sampler.py`
- Modify: `dispatch/backend/app/main.py`
- Delete: `dispatch/backend/app/api/navigation.py`
- Delete: `dispatch/backend/app/api/robot.py`
- Delete: `dispatch/backend/app/api/status.py`

- [ ] **Step 1: Create robots API**

```python
# dispatch/backend/app/api/robots.py

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/robots", tags=["robots"])


class RobotRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    control_url: str
    ws_url: str


@router.get("", response_model=ApiResponse)
async def list_robots(request: Request):
    db = request.app.state.db
    robots = await db.fetch_all("SELECT * FROM robots")
    for robot in robots:
        status_row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot["id"],))
        robot["status_data"] = None
        if status_row:
            import json
            robot["status_data"] = json.loads(status_row["status_json"])
    return ApiResponse(data={"robots": robots})


@router.get("/{robot_id}/status", response_model=ApiResponse)
async def get_robot_status(robot_id: str, request: Request):
    db = request.app.state.db
    status_row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot_id,))
    if not status_row:
        return ApiResponse(code=3002, message=f"Robot {robot_id} status not found")
    import json
    return ApiResponse(data={
        "robot_id": robot_id,
        "status": json.loads(status_row["status_json"]),
        "updated_at": status_row["updated_at"],
    })


@router.post("", response_model=ApiResponse)
async def register_robot(req: RobotRegister, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (req.id,))
    if existing:
        return ApiResponse(code=3001, message=f"Robot {req.id} already exists")
    await db.execute(
        "INSERT INTO robots (id, name, control_url, ws_url) VALUES (?, ?, ?, ?)",
        (req.id, req.name, req.control_url, req.ws_url),
    )
    if hasattr(request.app.state, 'status_monitor'):
        await request.app.state.status_monitor.register_robot(req.id, req.ws_url)
    return ApiResponse(data={"id": req.id, "name": req.name})


@router.delete("/{robot_id}", response_model=ApiResponse)
async def delete_robot(robot_id: str, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (robot_id,))
    if not existing:
        return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
    await db.execute("DELETE FROM robots WHERE id = ?", (robot_id,))
    await db.execute("DELETE FROM robot_status WHERE robot_id = ?", (robot_id,))
    return ApiResponse(data={"deleted": robot_id})
```

- [ ] **Step 2: Create task API (rewrite)**

```python
# dispatch/backend/app/api/task.py

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from app.models.task import TaskTemplate, TaskStep

router = APIRouter(prefix="/api/v1/dispatch/tasks", tags=["tasks"])


class TaskTemplateInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    steps: list[dict] = []


class TaskTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None


@router.get("", response_model=ApiResponse)
async def list_templates(request: Request):
    templates = await request.app.state.task_editor.list_all()
    return ApiResponse(data=templates)


@router.get("/{template_id}", response_model=ApiResponse)
async def get_template(template_id: str, request: Request):
    template = await request.app.state.task_editor.get(template_id)
    if not template:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data=template)


@router.post("", response_model=ApiResponse)
async def create_template(req: TaskTemplateInput, request: Request):
    existing = await request.app.state.task_editor.get(req.id)
    if existing:
        return ApiResponse(code=3001, message=f"Template {req.id} already exists")
    template = TaskTemplate(
        id=req.id, name=req.name, description=req.description,
        steps=[TaskStep(**s) for s in req.steps],
    )
    result = await request.app.state.task_editor.create(template)
    return ApiResponse(data=result)


@router.put("/{template_id}", response_model=ApiResponse)
async def update_template(template_id: str, req: TaskTemplateUpdate, request: Request):
    existing = await request.app.state.task_editor.get(template_id)
    if not existing:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    template = TaskTemplate(
        id=template_id,
        name=req.name or existing["name"],
        description=req.description or existing.get("description", ""),
        steps=[TaskStep(**s) for s in req.steps] if req.steps else [TaskStep(**s) for s in existing.get("steps", [])],
        version=existing.get("version", 1),
    )
    result = await request.app.state.task_editor.update(template)
    return ApiResponse(data=result)


@router.delete("/{template_id}", response_model=ApiResponse)
async def delete_template(template_id: str, request: Request):
    deleted = await request.app.state.task_editor.delete(template_id)
    if not deleted:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data={"deleted": template_id})
```

- [ ] **Step 3: Create executions API**

```python
# dispatch/backend/app/api/executions.py

from fastapi import APIRouter, Request
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch", tags=["executions"])


class ExecuteRequest(BaseModel):
    trigger_type: str = "manual"


@router.post("/tasks/{template_id}/execute", response_model=ApiResponse)
async def execute_task(template_id: str, req: ExecuteRequest, request: Request):
    result = await request.app.state.task_executor.execute(template_id, req.trigger_type)
    return ApiResponse(data=result)


@router.post("/tasks/{template_id}/execute/l2", response_model=ApiResponse)
async def execute_task_l2(template_id: str, request: Request):
    result = await request.app.state.task_executor.execute(template_id, "l2")
    return ApiResponse(data=result)


@router.get("/executions", response_model=ApiResponse)
async def list_executions(request: Request):
    executions = await request.app.state.task_executor.list_executions()
    return ApiResponse(data=executions)


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution(execution_id: int, request: Request):
    execution = await request.app.state.task_executor.get_execution(execution_id)
    if not execution:
        return ApiResponse(code=3002, message="Execution not found")
    return ApiResponse(data=execution)


@router.post("/executions/{execution_id}/cancel", response_model=ApiResponse)
async def cancel_execution(execution_id: int, request: Request):
    cancelled = await request.app.state.task_executor.cancel(execution_id)
    if not cancelled:
        return ApiResponse(code=3002, message="Execution not found or not running")
    return ApiResponse(data={"execution_id": execution_id, "status": "cancelled"})
```

- [ ] **Step 4: Create alarms API**

```python
# dispatch/backend/app/api/alarms.py

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from app.models.alarm import AlarmRule

router = APIRouter(prefix="/api/v1/dispatch/alarms", tags=["alarms"])


@router.get("", response_model=ApiResponse)
async def list_alarms(
    request: Request,
    level: str = Query(None),
    robot_id: str = Query(None),
    ack_status: str = Query(None),
):
    alarms = await request.app.state.alarm_service.list_alarms(
        level=level, robot_id=robot_id, ack_status=ack_status,
    )
    return ApiResponse(data=alarms)


@router.post("/{alarm_id}/ack", response_model=ApiResponse)
async def ack_alarm(alarm_id: str, request: Request):
    ok = await request.app.state.alarm_service.ack_alarm(alarm_id)
    if not ok:
        return ApiResponse(code=3002, message="Alarm not found")
    return ApiResponse(data={"alarm_id": alarm_id, "ack_status": "acked"})


@router.get("/rules", response_model=ApiResponse)
async def list_rules(request: Request):
    rules = await request.app.state.alarm_service.list_rules()
    return ApiResponse(data=rules)


class RuleInput(BaseModel):
    name: str
    category: str
    level: str
    condition_json: dict
    enabled: bool = True


@router.post("/rules", response_model=ApiResponse)
async def create_rule(req: RuleInput, request: Request):
    rule = AlarmRule(
        name=req.name, category=req.category, level=req.level,
        condition_json=req.condition_json, enabled=req.enabled,
    )
    result = await request.app.state.alarm_service.create_rule(rule)
    return ApiResponse(data=result)


@router.put("/rules/{rule_id}", response_model=ApiResponse)
async def update_rule(rule_id: int, req: RuleInput, request: Request):
    rule = AlarmRule(
        name=req.name, category=req.category, level=req.level,
        condition_json=req.condition_json, enabled=req.enabled,
    )
    ok = await request.app.state.alarm_service.update_rule(rule_id, rule)
    if not ok:
        return ApiResponse(code=3002, message="Rule not found")
    return ApiResponse(data={"id": rule_id})


@router.delete("/rules/{rule_id}", response_model=ApiResponse)
async def delete_rule(rule_id: int, request: Request):
    ok = await request.app.state.alarm_service.delete_rule(rule_id)
    if not ok:
        return ApiResponse(code=3002, message="Rule not found")
    return ApiResponse(data={"deleted": rule_id})
```

- [ ] **Step 5: Create logs API**

```python
# dispatch/backend/app/api/logs.py

from fastapi import APIRouter, Query, Request
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/logs", tags=["logs"])


@router.get("", response_model=ApiResponse)
async def list_logs(
    request: Request,
    level: str = Query(None),
    source: str = Query(None),
    robot_id: str = Query(None),
):
    logs = await request.app.state.log_service.list_logs(
        level=level, source=source, robot_id=robot_id,
    )
    return ApiResponse(data=logs)
```

- [ ] **Step 6: Rewrite sampler API**

```python
# dispatch/backend/app/api/sampler.py

from fastapi import APIRouter, Request
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/sampler", tags=["sampler"])


class SamplerCommand(BaseModel):
    command: str
    params: dict = {}


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand, request: Request):
    import time
    service = request.app.state.sampler_service
    if cmd.command == "start":
        result = await service.start()
    elif cmd.command == "stop":
        result = await service.stop()
    elif cmd.command == "query":
        result = await service.query()
    else:
        return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")
    if result.code == 0 and result.data:
        now = time.time()
        db = request.app.state.db
        await db.execute(
            "INSERT OR REPLACE INTO sampler_status (id, status, progress, status_json, last_update) VALUES (1, ?, ?, ?, ?)",
            (result.data.get("status", "idle"), result.data.get("progress", 0),
             str(result.data), now),
        )
    return result


@router.get("/status", response_model=ApiResponse)
async def sampler_status(request: Request):
    db = request.app.state.db
    row = await db.fetch_one("SELECT * FROM sampler_status WHERE id = 1")
    if not row:
        return ApiResponse(data={"status": "idle", "progress": 0})
    import json
    return ApiResponse(data={
        "status": row["status"],
        "progress": row["progress"],
        "status_data": json.loads(row["status_json"]) if row["status_json"] else {},
        "last_update": row["last_update"],
    })
```

- [ ] **Step 7: Rewrite dispatch main.py**

```python
# dispatch/backend/app/main.py

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.api.robots import router as robots_router
from app.api.task import router as task_router
from app.api.executions import router as executions_router
from app.api.alarms import router as alarms_router
from app.api.logs import router as logs_router
from app.api.sampler import router as sampler_router
from app.core.database import Database
from app.core.config import get_settings
from app.services.task_editor import TaskEditor
from app.services.task_executor import TaskExecutor
from app.services.alarm_service import AlarmService
from app.services.status_monitor import StatusMonitor
from app.services.log_service import LogService
from app.services.robot_proxy import RobotProxyService
from app.services.sampler_service import SamplerService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    db_path = os.environ.get("DATABASE_PATH", settings.database_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    await db.init()
    app.state.db = db

    # WS broadcast connections
    app.state.ws_connections: list[WebSocket] = []

    # Services
    robot_proxy = RobotProxyService()
    sampler_service = SamplerService()
    alarm_service = AlarmService(db)
    status_monitor = StatusMonitor(db, alarm_service)
    log_service = LogService(db)
    task_editor = TaskEditor(db)
    task_executor = TaskExecutor(db, robot_proxy, sampler_service)

    alarm_service._task_executor = task_executor

    app.state.robot_proxy = robot_proxy
    app.state.sampler_service = sampler_service
    app.state.alarm_service = alarm_service
    app.state.status_monitor = status_monitor
    app.state.log_service = log_service
    app.state.task_editor = task_editor
    app.state.task_executor = task_executor

    # Register robots from DB
    robots = await db.fetch_all("SELECT * FROM robots")
    for robot in robots:
        await status_monitor.register_robot(robot["id"], robot["ws_url"])

    # Seed default alarm rules if empty
    rules = await db.fetch_all("SELECT id FROM alarm_rules")
    if not rules:
        now = time.time()
        await db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("低电量警告", "battery", "warning", '{"field": "battery", "operator": "<", "value": 20}', 1, now),
        )
        await db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("电量耗尽", "battery", "critical", '{"field": "battery", "operator": "<", "value": 5}', 1, now),
        )

    logger.info("Dispatch system started, database: %s", db_path)
    yield
    # Shutdown
    await status_monitor.stop()
    await robot_proxy.close()
    await db.close()
    logger.info("Dispatch system stopped")


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Dispatch System", version="2.0.0", lifespan=lifespan)
    app.include_router(robots_router)
    app.include_router(task_router)
    app.include_router(executions_router)
    app.include_router(alarms_router)
    app.include_router(logs_router)
    app.include_router(sampler_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
```

- [ ] **Step 8: Delete old API files**

```bash
rm dispatch/backend/app/api/navigation.py
rm dispatch/backend/app/api/robot.py
rm dispatch/backend/app/api/status.py
```

- [ ] **Step 9: Delete old task_engine.py**

```bash
rm dispatch/backend/app/services/task_engine.py
```

- [ ] **Step 10: Commit**

```bash
git add dispatch/backend/app/
git rm dispatch/backend/app/api/navigation.py dispatch/backend/app/api/robot.py dispatch/backend/app/api/status.py dispatch/backend/app/services/task_engine.py
git commit -m "feat: refactor dispatch backend with new API routes and services"
```

### Task 3.9: Update dispatch config

**Files:**
- Modify: `dispatch/backend/app/core/config.py`

- [ ] **Step 1: Update config with mock robot URLs**

```python
# dispatch/backend/app/core/config.py
# Replace the Settings class:

class Settings(BaseSettings):
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    robots: list[RobotConfig] = [
        RobotConfig(
            id="robot_001",
            name="1号机器人",
            control_url="http://127.0.0.1:9001",
            ws_url="ws://127.0.0.1:9001/ws/v1/status",
        )
    ]

    sampler: SamplerConfig = SamplerConfig(ws_url="ws://127.0.0.1:9002")

    l2: L2Config = L2Config()

    database_path: str = "./data/dispatch.db"

    log_level: str = "INFO"
    log_dir: str = "./logs"
    log_retention_days: int = 30

    model_config = {"env_prefix": "", "case_sensitive": False}
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/core/config.py
git commit -m "feat: update dispatch config with mock robot URLs"
```

---

## Phase 4: 调度系统前端重构

### Task 4.1: Update router with new pages

**Files:**
- Modify: `dispatch/frontend/src/router.js`

- [ ] **Step 1: Rewrite router**

```javascript
// dispatch/frontend/src/router.js

import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import Sampler from './views/Sampler.vue'
import TaskEditor from './views/TaskEditor.vue'
import TaskExecution from './views/TaskExecution.vue'
import Alarms from './views/Alarms.vue'
import Logs from './views/Logs.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Dashboard },
    { path: '/sampler', component: Sampler },
    { path: '/tasks/editor', component: TaskEditor },
    { path: '/tasks/execution', component: TaskExecution },
    { path: '/alarms', component: Alarms },
    { path: '/logs', component: Logs },
  ],
})
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/frontend/src/router.js
git commit -m "feat: update dispatch router with new pages"
```

### Task 4.2: Update App.vue with new navigation

**Files:**
- Modify: `dispatch/frontend/src/App.vue`

- [ ] **Step 1: Rewrite App.vue**

```vue
<!-- dispatch/frontend/src/App.vue -->

<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="tech-sidebar">
      <div class="tech-title">调 度 系 统</div>
      <el-menu :default-active="$route.path" router background-color="transparent" text-color="#6b7b8d" active-text-color="#00d4ff">
        <el-menu-item index="/"><el-icon><Monitor /></el-icon><span>状态显示</span></el-menu-item>
        <el-menu-item index="/sampler"><el-icon><Setting /></el-icon><span>制样机控制</span></el-menu-item>
        <el-menu-item index="/tasks/editor"><el-icon><Edit /></el-icon><span>任务编排</span></el-menu-item>
        <el-menu-item index="/tasks/execution"><el-icon><VideoPlay /></el-icon><span>任务执行</span></el-menu-item>
        <el-menu-item index="/alarms"><el-icon><Bell /></el-icon><span>报警页面</span></el-menu-item>
        <el-menu-item index="/logs"><el-icon><Document /></el-icon><span>运行日志</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="tech-main"><router-view /></el-main>
  </el-container>
</template>

<script setup>
import { Monitor, Setting, Edit, VideoPlay, Bell, Document } from '@element-plus/icons-vue'
</script>
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/frontend/src/App.vue
git commit -m "feat: update App.vue navigation for new pages"
```

### Task 4.3: Create Dashboard page (status display)

**Files:**
- Create: `dispatch/frontend/src/views/Dashboard.vue` (overwrite)

- [ ] **Step 1: Write Dashboard with status cards**

```vue
<!-- dispatch/frontend/src/views/Dashboard.vue -->

<template>
  <div>
    <h2 class="page-title">状态显示</h2>
    <el-row :gutter="20">
      <el-col :span="12" v-for="robot in robots" :key="robot.id">
        <el-card class="status-card" :class="{ offline: robot.status === 'offline' }">
          <template #header>
            <div class="card-header">
              <span>{{ robot.name }} ({{ robot.id }})</span>
              <el-tag :type="robot.status === 'offline' ? 'danger' : 'success'" size="small">
                {{ robot.status === 'offline' ? '离线' : '在线' }}
              </el-tag>
            </div>
          </template>
          <div v-if="robot.status_data" class="status-grid">
            <div class="status-item"><label>电量</label><span>{{ robot.status_data.battery }}%</span></div>
            <div class="status-item"><label>充电</label><span>{{ robot.status_data.charging ? '是' : '否' }}</span></div>
            <div class="status-item"><label>使能</label><span>{{ robot.status_data.enabled ? '已使能' : '未使能' }}</span></div>
            <div class="status-item"><label>任务</label><span>{{ robot.status_data.task_status }}</span></div>
            <div class="status-item"><label>位置</label><span>x:{{ robot.status_data.position?.x?.toFixed(2) }} y:{{ robot.status_data.position?.y?.toFixed(2) }}</span></div>
            <div class="status-item"><label>夹爪L</label><span>{{ robot.status_data.gripper?.left?.state }}</span></div>
            <div class="status-item"><label>夹爪R</label><span>{{ robot.status_data.gripper?.right?.state }}</span></div>
            <div class="status-item"><label>手臂L</label><span>{{ robot.status_data.arm?.left?.status }}</span></div>
            <div class="status-item"><label>手臂R</label><span>{{ robot.status_data.arm?.right?.status }}</span></div>
            <div class="status-item"><label>错误码</label><span>{{ robot.status_data.error_code }}</span></div>
          </div>
          <div v-else class="no-data">等待数据...</div>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 24px;">制样机状态</h3>
    <el-card class="status-card">
      <div class="status-grid">
        <div class="status-item"><label>状态</label><span>{{ samplerData.status }}</span></div>
        <div class="status-item"><label>进度</label><span>{{ samplerData.progress }}%</span></div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'

const robots = ref([])
const samplerData = ref({ status: 'idle', progress: 0 })
let timer = null

async function fetchData() {
  try {
    const r = await api.get('/dispatch/robots')
    robots.value = r.data?.robots || []
  } catch (e) { /* ignore */ }
  try {
    const s = await api.get('/dispatch/sampler/status')
    if (s.data) samplerData.value = s.data
  } catch (e) { /* ignore */ }
}

onMounted(() => {
  fetchData()
  timer = setInterval(fetchData, 5000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.status-card { background: #0a1628; border: 1px solid #1a3a5c; margin-bottom: 16px; }
.status-card.offline { opacity: 0.6; }
.card-header { display: flex; justify-content: space-between; align-items: center; color: #b0c4de; }
.status-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
.status-item label { display: block; font-size: 12px; color: #6b7b8d; }
.status-item span { color: #e0e8f0; font-size: 14px; }
.no-data { color: #6b7b8d; text-align: center; padding: 20px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/frontend/src/views/Dashboard.vue
git commit -m "feat: rewrite Dashboard with robot and sampler status cards"
```

### Task 4.4: Create remaining view stubs

**Files:**
- Create: `dispatch/frontend/src/views/TaskEditor.vue`
- Create: `dispatch/frontend/src/views/TaskExecution.vue`
- Create: `dispatch/frontend/src/views/Alarms.vue`
- Create: `dispatch/frontend/src/views/Logs.vue`
- Modify: `dispatch/frontend/src/views/Sampler.vue`
- Delete: `dispatch/frontend/src/views/RobotControl.vue`
- Delete: `dispatch/frontend/src/views/Tasks.vue`

- [ ] **Step 1: Create TaskEditor.vue**

```vue
<!-- dispatch/frontend/src/views/TaskEditor.vue -->

<template>
  <div>
    <h2 class="page-title">任务编排</h2>
    <el-button type="primary" @click="showDialog = true">新建任务模板</el-button>

    <el-table :data="templates" style="margin-top: 16px;" class="tech-table" row-key="id">
      <el-table-column prop="id" label="ID" width="150" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="description" label="描述" />
      <el-table-column label="步骤数" width="80">
        <template #default="{ row }">
          {{ JSON.parse(row.steps_json || '[]').length }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200">
        <template #default="{ row }">
          <el-button size="small" @click="editTemplate(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteTemplate(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editingId ? '编辑任务' : '新建任务'" width="600px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="ID">
          <el-input v-model="form.id" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-form-item label="步骤">
          <div v-for="(step, idx) in form.steps" :key="idx" class="step-row">
            <el-select v-model="step.type" style="width: 120px">
              <el-option label="Workflow" value="workflow" />
              <el-option label="制样机" value="sampler" />
              <el-option label="延时" value="delay" />
            </el-select>
            <el-input v-model="step.id" placeholder="步骤ID" style="width: 120px; margin-left: 8px;" />
            <el-input v-model="step.label" placeholder="标签" style="width: 150px; margin-left: 8px;" />
            <el-button type="danger" size="small" @click="form.steps.splice(idx, 1)" circle>X</el-button>
          </div>
          <el-button size="small" @click="form.steps.push({ id: '', type: 'workflow', label: '', config: {} })">+ 添加步骤</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" @click="saveTemplate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const showDialog = ref(false)
const editingId = ref(null)
const form = ref({ id: '', name: '', description: '', steps: [] })

async function fetchTemplates() {
  try {
    const r = await api.get('/dispatch/tasks')
    templates.value = r.data || []
  } catch (e) { /* ignore */ }
}

function editTemplate(row) {
  editingId.value = row.id
  form.value = {
    id: row.id,
    name: row.name,
    description: row.description || '',
    steps: JSON.parse(row.steps_json || '[]'),
  }
  showDialog.value = true
}

async function saveTemplate() {
  try {
    if (editingId.value) {
      await api.put(`/dispatch/tasks/${editingId.value}`, form.value)
    } else {
      await api.post('/dispatch/tasks', form.value)
    }
    showDialog.value = false
    editingId.value = null
    fetchTemplates()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e.message || '保存失败')
  }
}

async function deleteTemplate(id) {
  try {
    await ElMessageBox.confirm('确认删除该模板?', '确认', { type: 'warning' })
    await api.delete(`/dispatch/tasks/${id}`)
    fetchTemplates()
    ElMessage.success('删除成功')
  } catch (e) { /* cancelled or error */ }
}

onMounted(fetchTemplates)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
.step-row { display: flex; align-items: center; margin-bottom: 8px; }
</style>
```

- [ ] **Step 2: Create TaskExecution.vue**

```vue
<!-- dispatch/frontend/src/views/TaskExecution.vue -->

<template>
  <div>
    <h2 class="page-title">任务执行</h2>

    <el-row :gutter="20">
      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>手动触发</span></template>
          <el-select v-model="selectedTemplate" placeholder="选择任务模板" style="width: 100%">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
          <el-button type="primary" style="margin-top: 12px; width: 100%" @click="executeTask" :loading="executing">
            执行任务
          </el-button>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>L2监听</span></template>
          <el-tag type="info">L2监听待启用</el-tag>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="exec-card">
          <template #header><span>快捷操作</span></template>
          <el-select v-model="quickRobot" placeholder="选择机器人" style="width: 100%">
            <el-option v-for="r in robots" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
          <el-select v-model="quickWorkflow" placeholder="选择工作流" style="width: 100%; margin-top: 8px">
            <el-option v-for="w in workflows" :key="w.name" :label="w.name" :value="w.name" />
          </el-select>
          <el-button type="warning" style="margin-top: 12px; width: 100%" @click="directCall">
            直接调用子任务
          </el-button>
        </el-card>
      </el-col>
    </el-row>

    <h3 style="margin-top: 24px; color: #00d4ff;">执行历史</h3>
    <el-table :data="executions" class="tech-table" row-key="id">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="task_template_id" label="模板" width="120" />
      <el-table-column prop="trigger_type" label="触发" width="80" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error_msg" label="错误信息" />
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="viewExecution(row.id)">详情</el-button>
          <el-button v-if="row.status === 'running'" size="small" type="danger" @click="cancelExecution(row.id)">取消</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const robots = ref([])
const workflows = ref([])
const executions = ref([])
const selectedTemplate = ref('')
const quickRobot = ref('robot_001')
const quickWorkflow = ref('')
const executing = ref(false)

function statusType(s) {
  return { completed: 'success', running: 'warning', failed: 'danger', cancelled: 'info' }[s] || 'info'
}

async function fetchData() {
  try { const r = await api.get('/dispatch/tasks'); templates.value = r.data || [] } catch (e) {}
  try { const r = await api.get('/dispatch/robots'); robots.value = r.data?.robots || [] } catch (e) {}
  try { const r = await api.get('/dispatch/executions'); executions.value = r.data || [] } catch (e) {}
}

async function executeTask() {
  if (!selectedTemplate.value) { ElMessage.warning('请选择任务模板'); return }
  executing.value = true
  try {
    await api.post(`/dispatch/tasks/${selectedTemplate.value}/execute`, { trigger_type: 'manual' })
    ElMessage.success('任务已触发')
    fetchData()
  } catch (e) { ElMessage.error(e.message || '执行失败') }
  executing.value = false
}

async function directCall() {
  ElMessage.info('直接调用: ' + quickRobot.value + ' / ' + quickWorkflow.value)
}

async function cancelExecution(id) {
  try {
    await api.post(`/dispatch/executions/${id}/cancel`)
    ElMessage.success('已取消')
    fetchData()
  } catch (e) { ElMessage.error(e.message || '取消失败') }
}

async function viewExecution(id) {
  try {
    const r = await api.get(`/dispatch/executions/${id}`)
    ElMessage.info(JSON.stringify(r.data))
  } catch (e) {}
}

onMounted(fetchData)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.exec-card { background: #0a1628; border: 1px solid #1a3a5c; margin-bottom: 16px; }
.tech-table { background: #0a1628; }
</style>
```

- [ ] **Step 3: Create Alarms.vue**

```vue
<!-- dispatch/frontend/src/views/Alarms.vue -->

<template>
  <div>
    <h2 class="page-title">报警页面</h2>
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="4">
        <el-select v-model="filterLevel" placeholder="级别" clearable @change="fetchAlarms">
          <el-option label="警告" value="warning" />
          <el-option label="严重" value="critical" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-select v-model="filterStatus" placeholder="状态" clearable @change="fetchAlarms">
          <el-option label="未确认" value="unack" />
          <el-option label="已确认" value="acked" />
        </el-select>
      </el-col>
    </el-row>

    <el-table :data="alarms" class="tech-table" row-key="id">
      <el-table-column prop="level" label="级别" width="80">
        <template #default="{ row }">
          <el-tag :type="row.level === 'critical' ? 'danger' : 'warning'" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="100" />
      <el-table-column prop="title" label="标题" width="200" />
      <el-table-column prop="message" label="消息" />
      <el-table-column prop="robot_id" label="机器人" width="120" />
      <el-table-column prop="ack_status" label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.ack_status === 'acked' ? 'success' : 'info'" size="small">
            {{ row.ack_status === 'acked' ? '已确认' : '未确认' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button v-if="row.ack_status === 'unack'" size="small" type="primary" @click="ackAlarm(row.id)">确认</el-button>
        </template>
      </el-table-column>
    </el-table>

    <h3 style="margin-top: 24px; color: #00d4ff;">报警规则</h3>
    <el-button size="small" type="primary" @click="showRuleDialog = true" style="margin-bottom: 12px;">添加规则</el-button>
    <el-table :data="rules" class="tech-table" row-key="id">
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="category" label="分类" width="120" />
      <el-table-column prop="level" label="级别" width="80" />
      <el-table-column prop="condition_json" label="条件" />
      <el-table-column label="操作" width="80">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="deleteRule(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showRuleDialog" title="添加报警规则" width="500px">
      <el-form :model="ruleForm" label-width="80px">
        <el-form-item label="名称"><el-input v-model="ruleForm.name" /></el-form-item>
        <el-form-item label="分类"><el-input v-model="ruleForm.category" /></el-form-item>
        <el-form-item label="级别">
          <el-select v-model="ruleForm.level"><el-option label="警告" value="warning" /><el-option label="严重" value="critical" /></el-select>
        </el-form-item>
        <el-form-item label="字段"><el-input v-model="ruleForm.field" placeholder="如: battery" /></el-form-item>
        <el-form-item label="运算符">
          <el-select v-model="ruleForm.operator">
            <el-option label="<" value="<" /><el-option label=">" value=">" /><el-option label="<=" value="<=" /><el-option label=">=" value=">=" /><el-option label="==" value="==" />
          </el-select>
        </el-form-item>
        <el-form-item label="阈值"><el-input-number v-model="ruleForm.value" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showRuleDialog = false">取消</el-button>
        <el-button type="primary" @click="createRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const alarms = ref([])
const rules = ref([])
const filterLevel = ref('')
const filterStatus = ref('')
const showRuleDialog = ref(false)
const ruleForm = ref({ name: '', category: '', level: 'warning', field: '', operator: '<', value: 0 })

async function fetchAlarms() {
  const params = {}
  if (filterLevel.value) params.level = filterLevel.value
  if (filterStatus.value) params.ack_status = filterStatus.value
  try { const r = await api.get('/dispatch/alarms', { params }); alarms.value = r.data || [] } catch (e) {}
}

async function fetchRules() {
  try { const r = await api.get('/dispatch/alarms/rules'); rules.value = r.data || [] } catch (e) {}
}

async function ackAlarm(id) {
  try {
    await api.post(`/dispatch/alarms/${id}/ack`)
    ElMessage.success('已确认')
    fetchAlarms()
  } catch (e) { ElMessage.error(e.message) }
}

async function createRule() {
  try {
    await api.post('/dispatch/alarms/rules', {
      name: ruleForm.value.name,
      category: ruleForm.value.category,
      level: ruleForm.value.level,
      condition_json: { field: ruleForm.value.field, operator: ruleForm.value.operator, value: ruleForm.value.value },
    })
    showRuleDialog.value = false
    fetchRules()
    ElMessage.success('规则已创建')
  } catch (e) { ElMessage.error(e.message) }
}

async function deleteRule(id) {
  try {
    await api.delete(`/dispatch/alarms/rules/${id}`)
    fetchRules()
  } catch (e) {}
}

onMounted(() => { fetchAlarms(); fetchRules() })
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
</style>
```

- [ ] **Step 4: Create Logs.vue**

```vue
<!-- dispatch/frontend/src/views/Logs.vue -->

<template>
  <div>
    <h2 class="page-title">运行日志</h2>
    <el-row :gutter="16" style="margin-bottom: 16px;">
      <el-col :span="4">
        <el-select v-model="filterLevel" placeholder="级别" clearable @change="fetchLogs">
          <el-option label="info" value="info" />
          <el-option label="warn" value="warn" />
          <el-option label="error" value="error" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-select v-model="filterSource" placeholder="来源" clearable @change="fetchLogs">
          <el-option label="控制系统" value="robot_control" />
          <el-option label="调度系统" value="dispatch" />
          <el-option label="制样机" value="sampler" />
        </el-select>
      </el-col>
    </el-row>

    <el-table :data="logs" class="tech-table" row-key="id" max-height="600">
      <el-table-column prop="level" label="级别" width="70">
        <template #default="{ row }">
          <el-tag :type="row.level === 'error' ? 'danger' : row.level === 'warn' ? 'warning' : 'info'" size="small">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="120" />
      <el-table-column prop="robot_id" label="机器人" width="100" />
      <el-table-column prop="message" label="消息" />
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ new Date(row.created_at * 1000).toLocaleString() }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'

const logs = ref([])
const filterLevel = ref('')
const filterSource = ref('')
let timer = null

async function fetchLogs() {
  const params = {}
  if (filterLevel.value) params.level = filterLevel.value
  if (filterSource.value) params.source = filterSource.value
  try { const r = await api.get('/dispatch/logs', { params }); logs.value = r.data || [] } catch (e) {}
}

onMounted(() => {
  fetchLogs()
  timer = setInterval(fetchLogs, 5000)
})

onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.tech-table { background: #0a1628; }
</style>
```

- [ ] **Step 5: Update Sampler.vue with placeholder**

```vue
<!-- dispatch/frontend/src/views/Sampler.vue -->

<template>
  <div>
    <h2 class="page-title">制样机控制</h2>
    <el-card class="exec-card">
      <template #header><span>制样机状态</span></template>
      <div class="status-grid">
        <div class="status-item"><label>状态</label><span>{{ status.status }}</span></div>
        <div class="status-item"><label>进度</label><span>{{ status.progress }}%</span></div>
      </div>
    </el-card>
    <el-card class="exec-card" style="margin-top: 16px;">
      <template #header><span>控制</span></template>
      <el-button type="primary" @click="sendCommand('start')">启动</el-button>
      <el-button type="danger" @click="sendCommand('stop')">停止</el-button>
    </el-card>
    <el-card class="exec-card" style="margin-top: 16px;">
      <template #header><span>功能待定</span></template>
      <p style="color: #6b7b8d;">制样机详细控制功能待后续确定</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

const status = ref({ status: 'idle', progress: 0 })

async function fetchStatus() {
  try { const r = await api.get('/dispatch/sampler/status'); if (r.data) status.value = r.data } catch (e) {}
}

async function sendCommand(cmd) {
  try {
    await api.post('/dispatch/sampler/command', { command: cmd, params: {} })
    ElMessage.success(`指令 ${cmd} 已发送`)
    fetchStatus()
  } catch (e) { ElMessage.error(e.message) }
}

onMounted(fetchStatus)
</script>

<style scoped>
.page-title { color: #00d4ff; margin-bottom: 20px; }
.exec-card { background: #0a1628; border: 1px solid #1a3a5c; }
.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.status-item label { display: block; font-size: 12px; color: #6b7b8d; }
.status-item span { color: #e0e8f0; font-size: 14px; }
</style>
```

- [ ] **Step 6: Delete old view files**

```bash
rm dispatch/frontend/src/views/RobotControl.vue
rm dispatch/frontend/src/views/Tasks.vue
```

- [ ] **Step 7: Commit**

```bash
git add dispatch/frontend/src/views/
git rm dispatch/frontend/src/views/RobotControl.vue dispatch/frontend/src/views/Tasks.vue
git commit -m "feat: add new dispatch frontend pages"
```

---

## Phase 5: 模拟系统

### Task 5.1: Create mock config

**Files:**
- Create: `dispatch/backend/app/mock/__init__.py`
- Create: `dispatch/backend/app/mock/config.py`

- [ ] **Step 1: Write mock config**

```python
# dispatch/backend/app/mock/config.py

class MockConfig:
    status_interval: float = 5.0
    step_duration_min: float = 1.0
    step_duration_max: float = 5.0
    alarm_probability: float = 0.15
    critical_alarm_ratio: float = 0.3
    error_probability: float = 0.05
    robot_id: str = "robot_001"
    port: int = 9001
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/mock/__init__.py dispatch/backend/app/mock/config.py
git commit -m "feat: add mock config for simulated control system"
```

### Task 5.2: Create mock robot control system

**Files:**
- Create: `dispatch/backend/app/mock/robot_mock.py`

- [ ] **Step 1: Write mock robot server**

```python
# dispatch/backend/app/mock/robot_mock.py

import asyncio
import json
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.mock.config import MockConfig

logger = logging.getLogger(__name__)

# ── Random data generators ──

def random_position():
    return {"x": round(random.uniform(0, 10), 2), "y": round(random.uniform(0, 10), 2), "theta": round(random.uniform(-3.14, 3.14), 2)}

def random_gripper():
    state = random.choice(["open", "closed"])
    return {
        "left": {"state": state, "force": round(random.uniform(0, 50), 1)},
        "right": {"state": random.choice(["open", "closed"]), "force": round(random.uniform(0, 50), 1)},
    }

def random_arm():
    return {
        "left": {"joint_angles": [round(random.uniform(-1.5, 1.5), 2) for _ in range(7)], "status": random.choice(["idle", "running"])},
        "right": {"joint_angles": [round(random.uniform(-1.5, 1.5), 2) for _ in range(7)], "status": random.choice(["idle", "running"])},
    }

def random_status():
    return {
        "position": random_position(),
        "current_map": "workshop_map",
        "lift_height": round(random.uniform(0, 500), 0),
        "gripper": random_gripper(),
        "battery": random.randint(10, 100),
        "charging": random.choice([True, False]),
        "enabled": True,
        "error_code": 0,
        "task_status": "idle",
        "arm": random_arm(),
    }


# ── FastAPI app ──

config = MockConfig()
connections: list[WebSocket] = []
active_executions: dict[str, dict] = {}

mock_app = FastAPI(title="Mock Robot Control System")


# Background task: push status periodically
async def status_pusher():
    while True:
        await asyncio.sleep(config.status_interval)
        frame = {
            "type": "status",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": random_status(),
        }
        await _broadcast(frame)


async def log_pusher():
    messages = [
        "Joint state updated", "Navigation status normal", "Battery level check OK",
        "Motor temperature normal", "Lidar scan completed", "IMU calibration OK",
        "ROS2 node heartbeat", "Camera frame captured",
    ]
    while True:
        await asyncio.sleep(random.uniform(3.0, 10.0))
        frame = {
            "type": "log",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "level": random.choice(["info", "info", "info", "warn"]),
                "source": random.choice(["move_node", "arm_node", "status_node", "camera_node"]),
                "node": "mock",
                "message": random.choice(messages),
            },
        }
        await _broadcast(frame)


async def _broadcast(frame: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(frame)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


# ── WebSocket endpoint ──

@mock_app.websocket("/ws/v1/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)


# ── HTTP API endpoints ──

@mock_app.get("/api/v1/robot/{robot_id}/status")
async def get_status(robot_id: str):
    return {"code": 0, "message": "ok", "data": random_status()}


@mock_app.get("/api/v1/robot/{robot_id}/workflows")
async def list_workflows(robot_id: str):
    return {"code": 0, "message": "ok", "data": [
        {"name": "sample_collect", "description": "取样流程", "step_count": 4, "version": 1},
        {"name": "move_to_charge", "description": "移动充电", "step_count": 2, "version": 1},
        {"name": "inspect_route", "description": "巡检路线", "step_count": 6, "version": 1},
    ]}


@mock_app.get("/api/v1/robot/{robot_id}/workflows/{name}")
async def get_workflow(robot_id: str, name: str):
    return {"code": 0, "message": "ok", "data": {
        "name": name,
        "description": f"Mock workflow: {name}",
        "steps": [
            {"id": "step_1", "type": "move", "label": "导航至目标点", "config": {"mode": "point"}},
            {"id": "step_2", "type": "upper_limb", "label": "手臂移动", "config": {"mode": "preset", "arm": "left", "preset_name": "home"}},
            {"id": "step_3", "type": "gripper", "label": "夹爪闭合", "config": {"arm": "left", "action": "close"}},
            {"id": "step_4", "type": "sleep", "label": "等待", "config": {"duration": 2.0}},
        ],
        "version": 1,
    }}


@mock_app.post("/api/v1/robot/{robot_id}/workflows/{name}/execute")
async def execute_workflow(robot_id: str, name: str):
    execution_id = str(uuid.uuid4())
    workflow_steps = [
        {"id": "step_1", "label": "导航至目标点", "total_steps": 4, "index": 1},
        {"id": "step_2", "label": "手臂移动", "total_steps": 4, "index": 2},
        {"id": "step_3", "label": "夹爪闭合", "total_steps": 4, "index": 3},
        {"id": "step_4", "label": "等待完成", "total_steps": 4, "index": 4},
    ]
    active_executions[execution_id] = {"name": name, "status": "running"}
    asyncio.create_task(_run_mock_workflow(execution_id, name, workflow_steps))
    return {"code": 0, "message": "ok", "data": {"execution_id": execution_id, "status": "started"}}


async def _run_mock_workflow(execution_id: str, name: str, steps: list[dict]):
    for step in steps:
        # Push "running"
        await _broadcast({
            "type": "workflow_step",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "workflow_name": name,
                "execution_id": execution_id,
                "step_id": step["id"],
                "step_index": step["index"],
                "total_steps": step["total_steps"],
                "status": "running",
                "message": f"Executing: {step['label']}",
                "data": {},
            },
        })

        # Simulate work
        duration = random.uniform(config.step_duration_min, config.step_duration_max)
        await asyncio.sleep(duration)

        # Random error
        if random.random() < config.error_probability:
            await _broadcast({
                "type": "workflow_step",
                "robot_id": config.robot_id,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "workflow_name": name,
                    "execution_id": execution_id,
                    "step_id": step["id"],
                    "step_index": step["index"],
                    "total_steps": step["total_steps"],
                    "status": "failed",
                    "message": f"Step failed: {step['label']}",
                    "data": {},
                },
            })
            active_executions[execution_id]["status"] = "failed"
            return

        # Random alarm
        if random.random() < config.alarm_probability:
            level = "critical" if random.random() < config.critical_alarm_ratio else "warning"
            await _broadcast({
                "type": "alarm",
                "robot_id": config.robot_id,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "alarm_id": str(uuid.uuid4()),
                    "level": level,
                    "category": random.choice(["arm", "chassis", "battery", "gripper"]),
                    "title": f"Mock {level} alarm",
                    "message": f"Simulated {level} during step: {step['label']}",
                    "source": "robot_control",
                },
            })

        # Push "completed"
        await _broadcast({
            "type": "workflow_step",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "workflow_name": name,
                "execution_id": execution_id,
                "step_id": step["id"],
                "step_index": step["index"],
                "total_steps": step["total_steps"],
                "status": "completed",
                "message": f"Completed: {step['label']}",
                "data": {},
            },
        })

    active_executions[execution_id]["status"] = "completed"


@mock_app.post("/api/v1/robot/{robot_id}/workflows/{name}/cancel")
async def cancel_workflow(robot_id: str, name: str):
    for eid, exec_data in list(active_executions.items()):
        if exec_data["name"] == name and exec_data["status"] == "running":
            exec_data["status"] = "cancelled"
    return {"code": 0, "message": "ok", "data": {"cancelled": True}}


@mock_app.get("/api/v1/robot/{robot_id}/workflows/executions/{execution_id}")
async def get_execution(robot_id: str, execution_id: str):
    if execution_id in active_executions:
        return {"code": 0, "message": "ok", "data": active_executions[execution_id]}
    return {"code": 3002, "message": "Execution not found", "data": None}


# Generic mock for other endpoints
@mock_app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path: str):
    return {"code": 0, "message": f"mock: {path}", "data": {}}


def create_mock_app():
    return mock_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.mock.robot_mock:mock_app", host="0.0.0.0", port=config.port, reload=False)
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/mock/robot_mock.py
git commit -m "feat: add mock robot control system with random data and alarms"
```

### Task 5.3: Create mock sampler

**Files:**
- Create: `dispatch/backend/app/mock/sampler_mock.py`

- [ ] **Step 1: Write mock sampler server**

```python
# dispatch/backend/app/mock/sampler_mock.py

import asyncio
import json
import random
import time
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

MOCK_PORT = 9002

connections: list[WebSocket] = []
sampler_state = {"status": "idle", "progress": 0, "current_step": ""}

mock_app = FastAPI(title="Mock Sampler")


async def _broadcast(frame: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(frame)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


async def status_pusher():
    while True:
        await asyncio.sleep(3.0)
        if sampler_state["status"] == "running":
            sampler_state["progress"] = min(100, sampler_state["progress"] + random.randint(5, 20))
            if sampler_state["progress"] >= 100:
                sampler_state["status"] = "completed"
                sampler_state["progress"] = 100
        frame = {
            "type": "status",
            "payload": sampler_state.copy(),
        }
        await _broadcast(frame)


@mock_app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "command":
                cmd = msg.get("command", "")
                if cmd == "start":
                    sampler_state["status"] = "running"
                    sampler_state["progress"] = 0
                    sampler_state["current_step"] = "processing"
                elif cmd == "stop":
                    sampler_state["status"] = "idle"
                    sampler_state["progress"] = 0
                    sampler_state["current_step"] = ""
                await ws.send_json({
                    "type": "response",
                    "request_id": msg.get("request_id", ""),
                    "payload": sampler_state.copy(),
                })
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)


@mock_app.post("/api/v1/sampler/command")
async def sampler_command(cmd: dict):
    command = cmd.get("command", "")
    if command == "start":
        sampler_state["status"] = "running"
        sampler_state["progress"] = 0
        sampler_state["current_step"] = "processing"
    elif command == "stop":
        sampler_state["status"] = "idle"
        sampler_state["progress"] = 0
        sampler_state["current_step"] = ""
    return {"code": 0, "message": "ok", "data": sampler_state.copy()}


@mock_app.get("/api/v1/sampler/status")
async def sampler_status():
    return {"code": 0, "message": "ok", "data": sampler_state.copy()}


def create_mock_app():
    return mock_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.mock.sampler_mock:mock_app", host="0.0.0.0", port=MOCK_PORT, reload=False)
```

- [ ] **Step 2: Commit**

```bash
git add dispatch/backend/app/mock/sampler_mock.py
git commit -m "feat: add mock sampler with status simulation"
```

---

## Phase 6: 集成测试与验证

### Task 6.1: Run shared tests

- [ ] **Step 1: Run all shared tests**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest shared/tests/ -v
```

Expected: All tests PASS

### Task 6.2: Run control system tests

- [ ] **Step 1: Run control system tests (excluding ROS2-dependent)**

```bash
cd /home/kty/Desktop/furance_robot && python -m pytest robot_control/backend/tests/ -v --ignore=robot_control/backend/tests/test_moveit_client.py --ignore=robot_control/backend/tests/test_ros2_factory.py --ignore=robot_control/backend/tests/test_ros2_nodes_api.py
```

Expected: All non-ROS2 tests PASS

### Task 6.3: Start mock systems and verify

- [ ] **Step 1: Start mock robot control system**

```bash
cd /home/kty/Desktop/furance_robot/dispatch/backend && python -m uvicorn app.mock.robot_mock:mock_app --host 0.0.0.0 --port 9001 &
```

- [ ] **Step 2: Verify mock robot HTTP API**

```bash
curl -s http://127.0.0.1:9001/api/v1/robot/robot_001/status | python -m json.tool
curl -s http://127.0.0.1:9001/api/v1/robot/robot_001/workflows | python -m json.tool
```

Expected: Returns random status data and workflow list

- [ ] **Step 3: Start mock sampler**

```bash
cd /home/kty/Desktop/furance_robot/dispatch/backend && python -m uvicorn app.mock.sampler_mock:mock_app --host 0.0.0.0 --port 9002 &
```

- [ ] **Step 4: Verify mock sampler**

```bash
curl -s http://127.0.0.1:9002/api/v1/sampler/status | python -m json.tool
```

Expected: Returns sampler status

### Task 6.4: Start dispatch system and verify

- [ ] **Step 1: Start dispatch backend**

```bash
cd /home/kty/Desktop/furance_robot/dispatch/backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

- [ ] **Step 2: Verify dispatch APIs**

```bash
# List robots
curl -s http://127.0.0.1:8000/api/v1/dispatch/robots | python -m json.tool

# List task templates
curl -s http://127.0.0.1:8000/api/v1/dispatch/tasks | python -m json.tool

# Create a task template
curl -s -X POST http://127.0.0.1:8000/api/v1/dispatch/tasks \
  -H "Content-Type: application/json" \
  -d '{"id":"test_task","name":"测试任务","description":"集成测试","steps":[{"id":"s1","type":"workflow","label":"取样","config":{"robot_id":"robot_001","workflow_name":"sample_collect"}},{"id":"s2","type":"delay","label":"等待","config":{"seconds":3}}]}' | python -m json.tool

# Execute the task
curl -s -X POST http://127.0.0.1:8000/api/v1/dispatch/tasks/test_task/execute \
  -H "Content-Type: application/json" \
  -d '{"trigger_type":"manual"}' | python -m json.tool

# List executions
curl -s http://127.0.0.1:8000/api/v1/dispatch/executions | python -m json.tool

# List alarms
curl -s http://127.0.0.1:8000/api/v1/dispatch/alarms | python -m json.tool

# List logs
curl -s http://127.0.0.1:8000/api/v1/dispatch/logs | python -m json.tool
```

Expected: All endpoints return valid JSON with code=0

### Task 6.5: Build and verify frontend

- [ ] **Step 1: Build frontend**

```bash
cd /home/kty/Desktop/furance_robot/dispatch/frontend && npm install && npm run build
```

Expected: Build succeeds without errors

### Task 6.6: Stop background processes

- [ ] **Step 1: Kill background servers**

```bash
pkill -f "uvicorn app.mock.robot_mock" 2>/dev/null; pkill -f "uvicorn app.mock.sampler_mock" 2>/dev/null; pkill -f "uvicorn app.main:app" 2>/dev/null
```
