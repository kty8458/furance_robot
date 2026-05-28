import asyncio
import json
import logging
import time
from app.core.database import Database
from app.clients.robot_ws import RobotWsClient

logger = logging.getLogger(__name__)


class StatusMonitor:
    def __init__(self, db: Database, alarm_service=None, ws_broadcast=None):
        self._db = db
        self._alarm_service = alarm_service
        self._ws_broadcast = ws_broadcast
        self._clients: dict[str, RobotWsClient] = {}
        self._robot_configs: dict[str, dict] = {}

    async def register_robot(self, robot_id: str, ws_url: str):
        self._robot_configs[robot_id] = {"ws_url": ws_url}
        client = RobotWsClient(ws_url)
        client.on("status", lambda frame, rid=robot_id: self._on_status(rid, frame))
        client.on("log", lambda frame, rid=robot_id: self._on_log(rid, frame))
        client.on("alarm", lambda frame, rid=robot_id: self._on_alarm(rid, frame))
        client.on("workflow_step", lambda frame, rid=robot_id: self._on_workflow_step(rid, frame))
        self._clients[robot_id] = client
        asyncio.create_task(self._connect_client(robot_id, client))

    async def _connect_client(self, robot_id: str, client: RobotWsClient):
        try:
            await client.connect()
        except Exception as e:
            logger.exception("WebSocket connection failed for robot %s: %s", robot_id, e)

    async def _on_status(self, robot_id: str, frame: dict):
        now = time.time()
        payload = frame.get("payload", {})
        await self._db.execute(
            "INSERT OR REPLACE INTO robot_status (robot_id, status_json, updated_at) VALUES (?, ?, ?)",
            (robot_id, json.dumps(payload), now),
        )
        if self._alarm_service:
            payload["robot_id"] = robot_id
            await self._alarm_service.check_conditions(payload)
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_log(self, robot_id: str, frame: dict):
        now = time.time()
        payload = frame.get("payload", {})
        await self._db.execute(
            "INSERT INTO operation_logs (source, robot_id, level, node, message, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("robot_control", robot_id, payload.get("level", "info"),
             payload.get("node", ""), payload.get("message", ""), now),
        )
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_alarm(self, robot_id: str, frame: dict):
        payload = frame.get("payload", {})
        if self._alarm_service:
            await self._alarm_service.create_alarm(
                robot_id=robot_id,
                source="robot",
                level=payload.get("level", "warning"),
                category=payload.get("category", "system"),
                title=payload.get("title", ""),
                message=payload.get("message", ""),
            )
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def _on_workflow_step(self, robot_id: str, frame: dict):
        if self._ws_broadcast:
            await self._ws_broadcast(frame)

    async def get_robot_status(self, robot_id: str) -> dict | None:
        row = await self._db.fetch_one(
            "SELECT * FROM robot_status WHERE robot_id = ?", (robot_id,)
        )
        if not row:
            return None
        return {
            "robot_id": row["robot_id"],
            "status": json.loads(row["status_json"]),
            "updated_at": row["updated_at"],
        }

    async def get_all_robot_status(self) -> list[dict]:
        robots = await self._db.fetch_all("SELECT * FROM robots")
        result = []
        for robot in robots:
            status_row = await self._db.fetch_one(
                "SELECT * FROM robot_status WHERE robot_id = ?", (robot["id"],)
            )
            robot["status_data"] = json.loads(status_row["status_json"]) if status_row else None
            robot["status"] = "online" if status_row else "offline"
            result.append(robot)
        return result

    async def stop(self):
        for client in self._clients.values():
            await client.disconnect()
