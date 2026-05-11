from furance_shared.protocol.http_schema import ApiResponse
from app.ros2.service_client import Ros2ServiceClientBase, MockRos2ServiceClient


class Ros2Manager:
    def __init__(self, ros2_client: Ros2ServiceClientBase | None = None):
        self._ros2 = ros2_client or MockRos2ServiceClient()

    async def list_nodes(self) -> ApiResponse:
        result = await self._ros2.call_service("/GetNodeList", {})
        return ApiResponse(data=result)

    async def start_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStart", {"node": node_name})
        return ApiResponse(data=result)

    async def stop_node(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStop", {"node": node_name})
        return ApiResponse(data=result)

    async def node_status(self, node_name: str) -> ApiResponse:
        result = await self._ros2.call_service("/NodeStatus", {"node": node_name})
        return ApiResponse(data=result)
