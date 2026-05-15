import logging

from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient

logger = logging.getLogger(__name__)


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


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
