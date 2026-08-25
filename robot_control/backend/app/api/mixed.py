import logging

from fastapi import APIRouter, Request
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/robot/{robot_id}/mixed", tags=["mixed"])

logger = logging.getLogger(__name__)


@router.get("/functions", response_model=ApiResponse)
async def list_mixed_functions(robot_id: str, request: Request):
    """获取可执行的混合功能列表 (来自 mixed_execution 服务的 /mixed/list)。

    返回 [{name, description, params_schema, moves_base}], 供工作流编辑器
    渲染混合功能步骤的下拉与动态参数表单。
    """
    ros2_client = request.app.state.ros2.service_client
    result = await ros2_client.call_service("/mixed/list", {})
    if not result.get("success"):
        return ApiResponse(code=3001, message=result.get("message", "Mixed service unavailable"))
    return ApiResponse(data=result.get("data", []))
