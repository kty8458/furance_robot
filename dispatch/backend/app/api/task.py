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
    from app.services.robot_proxy import RobotProxyService
    from app.services.sampler_service import SamplerService
    robot_proxy = RobotProxyService()
    sampler_service = SamplerService()
    result = await _engine.execute(req.template_id, req.robot_id, robot_proxy, sampler_service)
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