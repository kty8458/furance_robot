from fastapi import APIRouter
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse
from app.services.task_engine import TaskEngine

router = APIRouter(prefix="/api/v1/dispatch/tasks", tags=["task"])


class ExecuteRequest(BaseModel):
    template_id: str
    robot_id: str


_engine = TaskEngine()

MOCK_TEMPLATES = [
    {
        "id": "auto_sample",
        "name": "自动制样流程",
        "steps_json": {"steps": [
            {"order": 1, "action": "robot.home", "params": {}},
            {"order": 2, "action": "robot.grab", "params": {"target": "sample_pos"}},
            {"order": 3, "action": "robot.move", "params": {"map_id": "workshop_map", "waypoint_id": "wp_02"}},
            {"order": 4, "action": "sampler.start", "params": {}},
            {"order": 5, "action": "wait_sampler_complete", "params": {}},
        ]},
        "created_at": 1715400000.0,
        "updated_at": 1715400000.0,
    },
    {
        "id": "charge_and_wait",
        "name": "充电等待",
        "steps_json": {"steps": [
            {"order": 1, "action": "robot.move", "params": {"map_id": "workshop_map", "waypoint_id": "wp_03"}},
            {"order": 2, "action": "robot.charge", "params": {"action": "start"}},
            {"order": 3, "action": "delay", "params": {"seconds": 60}},
            {"order": 4, "action": "robot.charge", "params": {"action": "stop"}},
        ]},
        "created_at": 1715400000.0,
        "updated_at": 1715400000.0,
    },
]

MOCK_EXECUTIONS = [
    {
        "id": 1,
        "task_template_id": "auto_sample",
        "robot_id": "robot_001",
        "status": "completed",
        "started_at": 1715396000.0,
        "completed_at": 1715396120.0,
        "error_msg": None,
    },
]


@router.get("/templates", response_model=ApiResponse)
async def list_templates():
    templates = await _engine.list_templates()
    if not templates:
        templates = MOCK_TEMPLATES
    return ApiResponse(data=templates)


@router.post("/execute", response_model=ApiResponse)
async def execute_task(req: ExecuteRequest):
    from app.services.robot_proxy import RobotProxyService
    from app.services.sampler_service import SamplerService
    robot_proxy = RobotProxyService()
    sampler_service = SamplerService()
    result = await _engine.execute(req.template_id, req.robot_id, robot_proxy, sampler_service)
    return ApiResponse(data=result)


@router.get("/executions", response_model=ApiResponse)
async def list_executions():
    executions = await _engine.list_executions()
    if not executions:
        executions = MOCK_EXECUTIONS
    return ApiResponse(data=executions)


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution(execution_id: int):
    execution = await _engine.get_execution(execution_id)
    if not execution:
        return ApiResponse(code=3002, message="Execution not found")
    return ApiResponse(data=execution)
