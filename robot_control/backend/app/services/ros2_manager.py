from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


class Ros2Manager:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None):
        self._ros2 = ros2_client or MockRos2ServiceClient()

    async def list_nodes(self) -> ApiResponse:
        result = await self._ros2.call_service("/GetNodeList", {})
        return _check_result(result)

    async def start_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStart", {"name": node_name})
        return _check_result(result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStop", {"name": node_name})
        return _check_result(result)

    async def node_status(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStatus", {"name": node_name})
        return _check_result(result)
