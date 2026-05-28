import asyncio
import json
import logging
import websockets

logger = logging.getLogger(__name__)


class RobotWsClient:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None
        self._running = False
        self._handlers: dict[str, list] = {}

    def on(self, frame_type: str, handler):
        if frame_type not in self._handlers:
            self._handlers[frame_type] = []
        self._handlers[frame_type].append(handler)

    async def connect(self):
        self._running = True
        while self._running:
            try:
                self._ws = await websockets.connect(self._ws_url)
                logger.info("Connected to robot WS: %s", self._ws_url)
                async for raw in self._ws:
                    try:
                        frame = json.loads(raw)
                        frame_type = frame.get("type", "")
                        for handler in self._handlers.get(frame_type, []):
                            await handler(frame)
                        for handler in self._handlers.get("*", []):
                            await handler(frame)
                    except json.JSONDecodeError:
                        pass
            except Exception as e:
                logger.warning("Robot WS disconnected: %s, retrying in 5s", e)
                await asyncio.sleep(5.0)

    async def disconnect(self):
        self._running = False
        if self._ws:
            await self._ws.close()
