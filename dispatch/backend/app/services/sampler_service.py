from furance_shared.protocol.http_schema import ApiResponse
from app.clients.sampler_ws import SamplerWsClient
from app.core.config import get_settings


class SamplerService:
    def __init__(self, ws_url: str | None = None):
        settings = get_settings()
        self._client = SamplerWsClient(ws_url or settings.sampler.ws_url)
        self._connected = False

    async def ensure_connected(self):
        if not self._connected:
            try:
                await self._client.connect()
                self._connected = True
            except Exception:
                self._connected = False

    async def start(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("start")

    async def stop(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("stop")

    async def query(self) -> ApiResponse:
        await self.ensure_connected()
        return await self._client.send_command("query")

    async def wait_complete(self, poll_interval: float = 2.0, timeout: float = 600.0) -> ApiResponse:
        import asyncio
        import time
        start = time.time()
        while time.time() - start < timeout:
            resp = await self.query()
            if resp.data and resp.data.get("status") in ("completed", "error"):
                return resp
            await asyncio.sleep(poll_interval)
        return ApiResponse(code=1001, message="Sampler timeout")