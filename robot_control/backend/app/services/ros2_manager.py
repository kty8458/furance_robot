import logging
import os

from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient

logger = logging.getLogger(__name__)

LOG_BASE_DIR = os.path.join(os.path.expanduser('~'), '.ros', 'node_manager_logs')


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


def _find_latest_session() -> str | None:
    """Find the latest session directory under LOG_BASE_DIR."""
    if not os.path.isdir(LOG_BASE_DIR):
        return None
    sessions = [d for d in os.listdir(LOG_BASE_DIR)
                if os.path.isdir(os.path.join(LOG_BASE_DIR, d)) and not d.startswith('.')]
    if not sessions:
        return None
    sessions.sort(reverse=True)
    return os.path.join(LOG_BASE_DIR, sessions[0])


def _read_log_file(node_name: str, tail: int = 200) -> dict:
    """Read the last N lines from log file for a given node name."""
    session_dir = _find_latest_session()
    if not session_dir:
        return {"name": node_name, "logs": [], "total": 0}

    log_path = os.path.join(session_dir, f'{node_name}.log')
    if not os.path.exists(log_path):
        return {"name": node_name, "logs": [], "total": 0}

    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
        all_lines = [line.rstrip('\n') for line in all_lines]
        total = len(all_lines)
        result_lines = all_lines[-tail:] if tail < total else all_lines
        return {
            "name": node_name,
            "logs": result_lines,
            "total": total,
        }
    except Exception as e:
        logger.error("Failed to read log file %s: %s", log_path, e)
        return {"name": node_name, "logs": [], "total": 0}


class Ros2Manager:
    """ROS2 node and launch management via node_manager GenericCommand services."""

    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None):
        self._ros2 = ros2_client or MockRos2ServiceClient()
        self._is_mock = isinstance(self._ros2, MockRos2ServiceClient)

    async def list_nodes(self) -> ApiResponse:
        result = await self._ros2.call_service("/GetNodeList", {})
        if self._is_mock:
            return ApiResponse(data=[
                {"name": "arm_controller", "status": "stopped", "type": "node"},
                {"name": "gripper_controller", "status": "stopped", "type": "node"},
                {"name": "navigation_node", "status": "stopped", "type": "node"},
                {"name": "status_publisher", "status": "stopped", "type": "node"},
                {"name": "t1_moveit", "status": "stopped", "type": "launch"},
            ])
        return _check_result(result)

    async def start_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStart", {"name": node_name})
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "running"})
        return _check_result(result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStop", {"name": node_name})
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "stopped"})
        return _check_result(result)

    async def node_status(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStatus", {"name": node_name})
        if self._is_mock:
            return ApiResponse(data={"name": node_name, "status": "stopped"})
        return _check_result(result)

    async def node_logs(self, node_name: str, tail: int = 200) -> ApiResponse:
        if self._is_mock:
            return ApiResponse(data={
                "name": node_name, "logs": [f"[Mock] {node_name} log line {i}" for i in range(5)],
                "total": 5,
            })
        return ApiResponse(data=_read_log_file(node_name, tail))
