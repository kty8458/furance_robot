import logging
import time
from fastapi import WebSocket
from furance_shared.protocol.ws_frames import LogFrame


class LogService:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._logger = logging.getLogger("robot_control")

    def add_connection(self, ws: WebSocket):
        self._connections.append(ws)

    def remove_connection(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def push_log(self, source: str, level: str, message: str, node: str = "backend", robot_id: str = "robot_001"):
        frame = LogFrame(
            robot_id=robot_id,
            timestamp=int(time.time() * 1000),
            payload={"source": source, "level": level, "node": node, "message": message},
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
