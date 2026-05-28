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

    def set_db(self, db):
        self._db = db

    async def _get_or_create_client(self, robot_id: str) -> RobotHttpClient | None:
        if robot_id in self._clients:
            return self._clients[robot_id]
        if hasattr(self, '_db') and self._db:
            robot = await self._db.fetch_one("SELECT * FROM robots WHERE id = ?", (robot_id,))
            if robot:
                client = RobotHttpClient(robot["control_url"])
                self._clients[robot_id] = client
                return client
        return None

    async def forward(self, robot_id: str, path: str, json: dict | None = None) -> ApiResponse:
        client = await self._get_or_create_client(robot_id)
        if not client:
            return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
        try:
            return await client.post(path, json)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning("Robot %s unreachable (%s): %s", robot_id, path, e)
            return ApiResponse(code=1001, message=f"Robot {robot_id} 连接超时，控制系统不可达")

    async def forward_get(self, robot_id: str, path: str) -> ApiResponse:
        client = await self._get_or_create_client(robot_id)
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
