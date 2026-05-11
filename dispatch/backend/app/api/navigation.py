from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/dispatch", tags=["navigation"])

_proxy = RobotProxyService()

MOCK_MAPS = [
    {"id": "workshop_map", "name": "车间地图"},
    {"id": "lab_map", "name": "实验室地图"},
]

MOCK_WAYPOINTS = {
    "workshop_map": [
        {"id": "wp_01", "name": "上料点", "x": 1.0, "y": 2.0},
        {"id": "wp_02", "name": "制样机", "x": 3.0, "y": 4.0},
        {"id": "wp_03", "name": "充电桩", "x": 5.0, "y": 6.0},
        {"id": "wp_04", "name": "待命点", "x": 0.0, "y": 0.0},
    ],
    "lab_map": [
        {"id": "wp_10", "name": "入口", "x": 0.0, "y": 0.0},
        {"id": "wp_11", "name": "实验台", "x": 2.0, "y": 2.0},
    ],
}


@router.get("/maps", response_model=ApiResponse)
async def get_maps():
    try:
        robot_id = list(_proxy._clients.keys())[0]
        result = await _proxy.forward_get(robot_id, "/api/v1/maps")
        if result.code != 0:
            return ApiResponse(data=MOCK_MAPS)
        return result
    except (IndexError, Exception):
        return ApiResponse(data=MOCK_MAPS)


@router.get("/maps/{map_id}/waypoints", response_model=ApiResponse)
async def get_waypoints(map_id: str):
    try:
        robot_id = list(_proxy._clients.keys())[0]
        result = await _proxy.forward_get(robot_id, f"/api/v1/maps/{map_id}/waypoints")
        if result.code != 0:
            return ApiResponse(data=MOCK_WAYPOINTS.get(map_id, []))
        return result
    except (IndexError, Exception):
        return ApiResponse(data=MOCK_WAYPOINTS.get(map_id, []))
