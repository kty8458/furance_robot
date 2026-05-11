from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/status", tags=["status"])

_proxy = RobotProxyService()


@router.get("/robots", response_model=ApiResponse)
async def robots_status():
    results = {}
    for robot_id in _proxy._clients:
        try:
            resp = await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")
            results[robot_id] = resp.data
        except Exception:
            results[robot_id] = {"status": "offline"}
    return ApiResponse(data=results)