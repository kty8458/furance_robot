import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ChassisClient:
    """HTTP client for Magic底盘导航控制器.

    Manages Bearer token authentication with auto-retry on 401.
    Translates chassis response format {data, errCode, msg, successed}
    to project format.
    """

    def __init__(self, base_url: str, user_code: str, password: str, timeout: float = 15.0):
        self._base_url = base_url.rstrip("/")
        self._user_code = user_code
        self._password = password
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self):
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _translate(self, body: dict) -> dict[str, Any]:
        if not body.get("successed", False):
            return {
                "success": False,
                "message": body.get("msg", "chassis request failed"),
                "data": body.get("data"),
            }
        return {"success": True, "message": body.get("msg", "ok"), "data": body.get("data")}

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        headers = self._headers()
        if method == "POST" and "json" in kwargs:
            headers["Content-Type"] = "application/json"
        kwargs.setdefault("headers", headers)

        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.RequestError as e:
            logger.error("Chassis request error: %s", e)
            return {"success": False, "message": f"底盘连接失败: {e}"}

        # Auth failure — retry once
        if resp.status_code == 401 and self._token:
            logger.info("Chassis auth error, re-authenticating")
            auth_result = await self.authenticate(force=True)
            if not auth_result.get("success"):
                return auth_result
            kwargs["headers"] = self._headers()
            try:
                resp = await self._client.request(method, url, **kwargs)
            except httpx.RequestError as e:
                return {"success": False, "message": f"底盘连接失败: {e}"}

        if resp.status_code >= 400:
            logger.error("Chassis error %s: %s", resp.status_code, resp.text[:200])
            return {"success": False, "message": f"底盘返回错误 ({resp.status_code})"}

        try:
            body = resp.json()
        except Exception:
            return {"success": False, "message": "底盘响应解析失败"}

        return self._translate(body)

    async def authenticate(self, force: bool = False) -> dict[str, Any]:
        if self._token and not force:
            return {"success": True, "message": "already authenticated"}

        url = f"{self._base_url}/auth/token"
        try:
            resp = await self._client.post(
                url,
                json={"userCode": self._user_code, "password": self._password},
                headers={"Content-Type": "application/json"},
            )
        except httpx.RequestError as e:
            logger.error("Chassis auth connection error: %s", e)
            return {"success": False, "message": f"底盘连接失败: {e}"}

        if resp.status_code >= 400:
            logger.error("Chassis auth failed: status=%s body=%s", resp.status_code, resp.text[:200])
            self._token = None
            return {"success": False, "message": f"底盘认证失败: {resp.text[:100]}"}

        try:
            body = resp.json()
        except Exception:
            self._token = None
            return {"success": False, "message": "底盘认证响应解析失败"}

        if not body.get("successed", False):
            logger.error("Chassis auth failed: %s", body.get("msg"))
            self._token = None
            return {"success": False, "message": f"底盘认证失败: {body.get('msg', '未知错误')}"}

        self._token = body.get("data", {}).get("token")
        logger.info("Chassis authenticated successfully")
        return {"success": True, "message": "authenticated", "data": body.get("data")}

    async def _ensure_token(self):
        if not self._token:
            await self.authenticate()

    async def get_maps(self) -> dict[str, Any]:
        await self._ensure_token()
        return await self._request("GET", "/data/list_maps")

    async def get_positions(self, map_name: str, type_: str = "") -> dict[str, Any]:
        await self._ensure_token()
        params = {"map_name": map_name}
        if type_:
            params["type"] = type_
        return await self._request("GET", "/data/poslist", params=params)

    async def get_graph_paths(self, map_name: str) -> dict[str, Any]:
        await self._ensure_token()
        return await self._request("GET", "/data/graph_list", params={"map_name": map_name})

    async def get_record_paths(self, map_name: str) -> dict[str, Any]:
        await self._ensure_token()
        return await self._request("GET", "/data/record_list", params={"map_name": map_name})

    async def start_task(self, body: dict) -> dict[str, Any]:
        await self._ensure_token()
        logger.info("EVENT chassis_task_start body=%s", body)
        result = await self._request("POST", "/task_queue/start", json=body)
        logger.info("EVENT chassis_task_start_result success=%s msg=%s",
                    result.get("success"), result.get("message"))
        return result

    async def stop_task(self) -> dict[str, Any]:
        await self._ensure_token()
        logger.info("EVENT chassis_task_stop")
        return await self._request("POST", "/task_queue/stop")

    async def is_task_finished(self) -> dict[str, Any]:
        """检查是否有任务正在执行 (GET /task_queue/task/is_finished).

        Returns data=True → 当前无任务；data=False → 当前有任务在执行。
        """
        await self._ensure_token()
        return await self._request("GET", "/task_queue/task/is_finished")

    async def is_queue_finished(self) -> dict[str, Any]:
        """检查任务队列执行状态 (GET /task_queue/is_finished).

        Returns data=1 → 正在执行；data=0 → 没有执行。
        msg='不能到达' 表示导航失败。
        """
        await self._ensure_token()
        return await self._request("GET", "/task_queue/is_finished")

    async def get_task_logs(self, map_name: str, start_time: str, end_time: str) -> dict[str, Any]:
        await self._ensure_token()
        return await self._request(
            "GET", "/task_queue/log",
            params={"map_name": map_name, "start_time": start_time, "end_time": end_time},
        )

    async def recharge(self, map_name: str, point_name: str) -> dict[str, Any]:
        await self._ensure_token()
        return await self._request("POST", "/cmd/recharge", json={"map_name": map_name, "point_name": point_name})

    async def get_hardware_status(self) -> dict[str, Any]:
        """Poll chassis hardware status (position, battery, charge, map)."""
        await self._ensure_token()
        return await self._request("GET", "/real_time_data/robot_hardware_status")


class MockChassisClient:
    """Mock chassis client for development without hardware."""

    async def close(self):
        pass

    async def authenticate(self, force: bool = False) -> dict[str, Any]:
        return {"success": True, "message": "authenticated (mock)"}

    async def get_maps(self) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": [
            {"id": "workshop", "name": "车间地图"},
            {"id": "warehouse", "name": "仓库地图"},
        ]}

    async def get_positions(self, map_name: str, type_: str = "") -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": [
            {"name": "A点", "angle": 0, "worldPose": {"position": {"x": 1.0, "y": 2.0, "z": 0}}},
            {"name": "B点", "angle": 90, "worldPose": {"position": {"x": 3.0, "y": 4.0, "z": 0}}},
            {"name": "充电点", "angle": 180, "worldPose": {"position": {"x": 0.0, "y": 0.0, "z": 0}}},
        ]}

    async def get_graph_paths(self, map_name: str) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": [
            {"name": "路径1"}, {"name": "路径2"},
        ]}

    async def get_record_paths(self, map_name: str) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": [
            {"name": "录制路径1"},
        ]}

    async def start_task(self, body: dict) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": {"task_id": "mock-001"}}

    async def stop_task(self) -> dict[str, Any]:
        return {"success": True, "message": "ok"}

    async def is_task_finished(self) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": True}

    async def get_task_logs(self, map_name: str, start_time: str, end_time: str) -> dict[str, Any]:
        return {"success": True, "message": "ok", "data": "Mock task log"}

    async def recharge(self, map_name: str, point_name: str) -> dict[str, Any]:
        return {"success": True, "message": "ok"}

    async def get_hardware_status(self) -> dict[str, Any]:
        import random
        return {
            "success": True, "message": "ok",
            "data": {
                "world_x": round(random.uniform(-5, 5), 2),
                "world_y": round(random.uniform(-5, 5), 2),
                "theta": round(random.uniform(-3.14, 3.14), 2),
                "battery_percentage": random.randint(30, 95),
                "charge": random.choice([0, 1]),
                "map_name": "workshop_map",
            },
        }
