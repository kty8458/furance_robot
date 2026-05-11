from fastapi import APIRouter
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/dispatch", tags=["status"])

_proxy = RobotProxyService()


@router.get("/robots", response_model=ApiResponse)
async def robots_status():
    results = {}
    for robot_id in _proxy._clients:
        try:
            resp = await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")
            results[robot_id] = resp.data
        except Exception:
            results[robot_id] = _mock_robot_status(robot_id)
    # If no clients connected (control system unreachable), return mock
    if not results:
        results["robot_001"] = _mock_robot_status("robot_001")
    return ApiResponse(data=results)


def _mock_robot_status(robot_id: str) -> dict:
    return {
        "position": {"x": 1.23, "y": 4.56, "theta": 0.78},
        "current_map": "workshop_map",
        "battery": 85,
        "charging": False,
        "enabled": True,
        "error_code": 0,
        "task_status": "idle",
    }
