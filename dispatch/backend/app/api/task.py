from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import BusinessError, ErrorCode
from app.services.task_engine import TaskEngine, TaskStep, TaskTemplate

router = APIRouter(prefix="/api/v1/dispatch/tasks", tags=["task"])


class StepInput(BaseModel):
    order: int
    action: str
    params: dict = {}


class TemplateCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    steps: list[StepInput]


class TemplateUpdate(BaseModel):
    name: str | None = None
    steps: list[StepInput] | None = None


class ExecuteRequest(BaseModel):
    template_id: str
    robot_id: str


def _get_engine(request: Request) -> TaskEngine:
    return TaskEngine(db=request.app.state.db)


# ── Template CRUD ──


@router.get("/templates", response_model=ApiResponse)
async def list_templates(request: Request):
    templates = await _get_engine(request).list_templates()
    return ApiResponse(data=templates)


@router.get("/templates/{template_id}", response_model=ApiResponse)
async def get_template(template_id: str, request: Request):
    template = await _get_engine(request).get_template(template_id)
    if not template:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data=template)


@router.post("/templates", response_model=ApiResponse)
async def create_template(req: TemplateCreate, request: Request):
    existing = await _get_engine(request).get_template(req.id)
    if existing:
        return ApiResponse(code=3001, message=f"Template {req.id} already exists")
    template = TaskTemplate(
        id=req.id,
        name=req.name,
        steps=[TaskStep(**s.model_dump()) for s in req.steps],
    )
    result = await _get_engine(request).create_template(template)
    return ApiResponse(data=result)


@router.put("/templates/{template_id}", response_model=ApiResponse)
async def update_template(template_id: str, req: TemplateUpdate, request: Request):
    existing = await _get_engine(request).get_template(template_id)
    if not existing:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    # Merge existing with updates
    import json
    old_steps = json.loads(existing["steps_json"]).get("steps", [])
    template = TaskTemplate(
        id=template_id,
        name=req.name or existing["name"],
        steps=[TaskStep(**s.model_dump()) for s in req.steps] if req.steps else [TaskStep(**s) for s in old_steps],
    )
    result = await _get_engine(request).update_template(template)
    return ApiResponse(data=result)


@router.delete("/templates/{template_id}", response_model=ApiResponse)
async def delete_template(template_id: str, request: Request):
    deleted = await _get_engine(request).delete_template(template_id)
    if not deleted:
        return ApiResponse(code=3002, message=f"Template {template_id} not found")
    return ApiResponse(data={"deleted": template_id})


# ── Execution ──


@router.post("/execute", response_model=ApiResponse)
async def execute_task(req: ExecuteRequest, request: Request):
    engine = _get_engine(request)
    template = await engine.get_template(req.template_id)
    if not template:
        return ApiResponse(code=3002, message=f"Template {req.template_id} not found")
    from app.services.robot_proxy import RobotProxyService
    from app.services.sampler_service import SamplerService
    robot_proxy = RobotProxyService()
    sampler_service = SamplerService()
    result = await engine.execute(req.template_id, req.robot_id, robot_proxy, sampler_service)
    return ApiResponse(data=result)


@router.get("/executions", response_model=ApiResponse)
async def list_executions(request: Request):
    executions = await _get_engine(request).list_executions()
    return ApiResponse(data=executions)


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution(execution_id: int, request: Request):
    execution = await _get_engine(request).get_execution(execution_id)
    if not execution:
        return ApiResponse(code=3002, message="Execution not found")
    return ApiResponse(data=execution)


@router.post("/executions/{execution_id}/cancel", response_model=ApiResponse)
async def cancel_execution(execution_id: int, request: Request):
    cancelled = await _get_engine(request).cancel_execution(execution_id)
    if not cancelled:
        return ApiResponse(code=3002, message="Execution not found or not running")
    return ApiResponse(data={"execution_id": execution_id, "status": "cancelled"})
