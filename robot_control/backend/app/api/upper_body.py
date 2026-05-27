from fastapi import APIRouter, HTTPException, Request
from furance_shared.models.command import WaistControlCommand, AscendControlCommand, HeadControlCommand
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/robot/{robot_id}/upper-body", tags=["upper-body"])


def _get_client(request: Request):
    return request.app.state.ros2.upper_body_client


@router.post("/waist", response_model=ApiResponse)
async def waist_control(robot_id: str, cmd: WaistControlCommand, request: Request):
    result = await _get_client(request).waist_control(cmd.waist_angle, cmd.waist_speed)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "腰部控制失败"))
    return ApiResponse(data=result)


@router.post("/ascend", response_model=ApiResponse)
async def ascend_control(robot_id: str, cmd: AscendControlCommand, request: Request):
    result = await _get_client(request).ascend_control(cmd.ascend_pos, cmd.ascend_speed)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "头部偏转失败"))
    return ApiResponse(data=result)


@router.post("/head", response_model=ApiResponse)
async def head_control(robot_id: str, cmd: HeadControlCommand, request: Request):
    result = await _get_client(request).head_control(cmd.head_angle, cmd.head_speed)
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "头部俯仰失败"))
    return ApiResponse(data=result)
