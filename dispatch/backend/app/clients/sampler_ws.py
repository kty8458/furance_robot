import asyncio
import json
import uuid
import websockets
from furance_shared.protocol.http_schema import ApiResponse


class SamplerWsClient:
    def __init__(self, ws_url: str):
        self._ws_url = ws_url
        self._ws = None

    async def connect(self):
        self._ws = await websockets.connect(self._ws_url)

    async def disconnect(self):
        if self._ws:
            await self._ws.close()

    async def send_command(self, command: str, params: dict | None = None) -> ApiResponse:
        if not self._ws:
            await self.connect()
        request_id = str(uuid.uuid4())
        msg = {
            "type": "command",
            "command": command,
            "params": params or {},
            "request_id": request_id,
        }
        await self._ws.send(json.dumps(msg))
        response = await asyncio.wait_for(self._ws.recv(), timeout=60.0)
        data = json.loads(response)
        return ApiResponse(
            code=0 if data.get("type") != "error" else 1,
            data=data.get("payload", {}),
        )