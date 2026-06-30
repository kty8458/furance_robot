from fastapi import APIRouter, HTTPException, Request
from furance_shared.models.workflow import Workflow, WorkflowExecuteRequest
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.workflow_service import WorkflowService
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/robot/{robot_id}/workflows", tags=["workflows"])


def _get_workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


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


def _validate_robot_ready(request: Request, robot_id: str, workflow_steps: list) -> str | None:
    """Pre-flight validation. Returns error message if not ready, None if OK.

    Checks:
      - Status data available (control system has received robot status)
      - Arms enabled if workflow contains upper_limb or upper_body steps
      - Battery > 10% and not in error if workflow contains move steps
    """
    status_service = request.app.state.status_service
    status = status_service.get_latest(robot_id)
    if not status:
        return "机器人状态未就绪，请先确认控制系统已连接"

    needs_arm = any(s.type in ("upper_limb", "upper_body", "gripper") for s in workflow_steps)
    needs_move = any(s.type == "move" for s in workflow_steps)

    if needs_arm and not status.get("enabled", False):
        return "上肢未使能，请先使能机械臂"

    if status.get("error_code", 0) != 0:
        return f"机器人存在告警（error_code={status.get('error_code')}），请先清除告警"

    if needs_move:
        battery = status.get("battery", 0)
        if battery > 0 and battery < 10:
            return f"电量过低（{battery}%），无法执行包含移动的工作流"
        if not status.get("current_map"):
            return "底盘未加载地图，无法执行移动步骤"

    return None


@router.post("/{name}/execute", response_model=ApiResponse)
async def execute_workflow(robot_id: str, name: str, req: WorkflowExecuteRequest, request: Request):
    try:
        service = _get_workflow_service(request)
        workflow = service.get_workflow(robot_id, name)

        error = _validate_robot_ready(request, robot_id, workflow.steps)
        if error:
            return ApiResponse(code=2001, message=error)

        execution_id = service.start_execution(robot_id, name, req)
        return ApiResponse(data={"execution_id": execution_id, "status": "started"})
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.post("/{name}/cancel", response_model=ApiResponse)
async def cancel_workflow(robot_id: str, name: str, request: Request):
    service = _get_workflow_service(request)
    cancelled = await service.cancel_workflow()
    return ApiResponse(data={"cancelled": cancelled})


@router.post("/executions/{execution_id}/next", response_model=ApiResponse)
async def trigger_next_step(robot_id: str, execution_id: str, request: Request):
    """手动模式: 触发下一步执行."""
    service = _get_workflow_service(request)
    ok = service.trigger_next_step(execution_id)
    if not ok:
        return ApiResponse(code=2002, message="Execution not in manual mode or not found")
    return ApiResponse(data={"triggered": True})


@router.post("/executions/{execution_id}/update-step", response_model=ApiResponse)
async def update_pending_step(robot_id: str, execution_id: str, req: dict, request: Request):
    """手动模式: 修改未执行步骤的参数. body: {step_id, config}."""
    service = _get_workflow_service(request)
    step_id = req.get("step_id", "")
    config = req.get("config", {})
    ok = service.update_pending_step(execution_id, step_id, config)
    if not ok:
        return ApiResponse(code=2003, message="Execution not in manual mode or not found")
    return ApiResponse(data={"updated": True, "step_id": step_id})


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution_status(robot_id: str, execution_id: str, request: Request):
    service = _get_workflow_service(request)
    status = service.get_execution_status(execution_id)
    return ApiResponse(data=status)
