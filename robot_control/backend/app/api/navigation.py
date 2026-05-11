from fastapi import APIRouter
from furance_shared.models.command import MoveCommand
from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1", tags=["navigation"])

_ros2_client = MockRos2ServiceClient()


@router.get("/maps", response_model=ApiResponse)
async def get_maps():
    result = await _ros2_client.call_service("/GetMapList", {})
    return ApiResponse(data=result)


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str):
    result = await _ros2_client.call_service("/GetWaypointList", {"map_id": map_id})
    return ApiResponse(data=result)


@router.post("/robot/{robot_id}/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand):
    result = await _ros2_client.call_service("/MoveCommand", cmd.model_dump())
    return ApiResponse(data=result)
