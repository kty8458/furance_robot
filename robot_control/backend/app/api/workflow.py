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
        execution_id = service.start_execution(robot_id, name, req)
        return ApiResponse(data={"execution_id": execution_id, "status": "started"})
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.post("/{name}/cancel", response_model=ApiResponse)
async def cancel_workflow(robot_id: str, name: str, request: Request):
    service = _get_workflow_service(request)
    cancelled = await service.cancel_workflow()
    return ApiResponse(data={"cancelled": cancelled})


@router.get("/executions/{execution_id}", response_model=ApiResponse)
async def get_execution_status(robot_id: str, execution_id: str, request: Request):
    service = _get_workflow_service(request)
    status = service.get_execution_status(execution_id)
    return ApiResponse(data=status)
