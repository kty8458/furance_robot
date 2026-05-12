import httpx
from furance_shared.protocol.http_schema import ApiResponse


class RobotHttpClient:
    def __init__(self, base_url: str, timeout: float = 5.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def post(self, path: str, json: dict | None = None) -> ApiResponse:
        url = f"{self._base_url}{path}"
        resp = await self._client.post(url, json=json)
        resp.raise_for_status()
        return ApiResponse(**resp.json())

    async def get(self, path: str) -> ApiResponse:
        url = f"{self._base_url}{path}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return ApiResponse(**resp.json())

    async def close(self):
        await self._client.aclose()
