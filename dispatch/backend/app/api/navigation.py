from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1", tags=["navigation"])

_proxy = RobotProxyService()


@router.get("/maps", response_model=ApiResponse)
async def get_maps():
    robot_id = list(_proxy._clients.keys())[0]
    return await _proxy.forward_get(robot_id, "/api/v1/maps")


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str):
    robot_id = list(_proxy._clients.keys())[0]
    return await _proxy.forward_get(robot_id, f"/api/v1/maps/{map_id}/waypoints")