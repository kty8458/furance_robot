import logging

import httpx
from furance_shared.protocol.http_schema import ApiResponse
from app.clients.robot_http import RobotHttpClient
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RobotProxyService:
    def __init__(self):
        self._clients: dict[str, RobotHttpClient] = {}
        settings = get_settings()
        for robot in settings.robots:
            self._clients[robot.id] = RobotHttpClient(robot.control_url)

    async def forward(self, robot_id: str, path: str, json: dict | None = None) -> ApiResponse:
        client = self._clients.get(robot_id)
        if not client:
            return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
        try:
            return await client.post(path, json)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Robot %s unreachable (%s): %s", robot_id, path, e)
            return ApiResponse(code=1001, message=f"Robot {robot_id} 连接超时，控制系统不可达")

    async def forward_get(self, robot_id: str, path: str) -> ApiResponse:
        client = self._clients.get(robot_id)
        if not client:
            return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
        try:
            return await client.get(path)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Robot %s unreachable (%s): %s", robot_id, path, e)
            return ApiResponse(code=1001, message=f"Robot {robot_id} 连接超时，控制系统不可达")

    async def close(self):
        for client in self._clients.values():
            await client.close()
