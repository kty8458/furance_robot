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
