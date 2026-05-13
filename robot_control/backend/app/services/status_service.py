import asyncio
import time
from fastapi import WebSocket
from furance_shared.protocol.ws_frames import StatusFrame, ErrorFrame, WsFrameType
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState


class StatusService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._latest: dict[str, dict] = {}

    def add_connection(self, ws: WebSocket):
        self._connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        self._connections.remove(ws)

    def get_latest(self, robot_id: str) -> dict | None:
        return self._latest.get(robot_id)

    async def push_status(self, robot_id: str, status_data: dict):
        self._latest[robot_id] = status_data
        frame = StatusFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload=status_data,
        )
        await self._broadcast(frame.model_dump())

    async def push_error(self, robot_id: str, error_code: int, error_msg: str, source: str):
        frame = ErrorFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload={"error_code": error_code, "error_msg": error_msg, "source": source},
        )
        await self._broadcast(frame.model_dump())

    async def _broadcast(self, data: dict):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)
