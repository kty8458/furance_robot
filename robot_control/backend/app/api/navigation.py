from fastapi import APIRouter, Request
from furance_shared.models.command import MoveCommand
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["navigation"])


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


@router.get("/maps", response_model=ApiResponse)
async def get_maps(request: Request):
    client = request.app.state.ros2.service_client
    result = await client.call_service("/GetMapList", {})
    return _check_result(result)


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str, request: Request):
    client = request.app.state.ros2.service_client
    result = await client.call_service("/GetWaypointList", {"map_id": map_id})
    return _check_result(result)


@router.post("/robot/{robot_id}/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand, request: Request):
    client = request.app.state.ros2.service_client
    result = await client.call_service("/MoveCommand", cmd.model_dump())
    return _check_result(result)
