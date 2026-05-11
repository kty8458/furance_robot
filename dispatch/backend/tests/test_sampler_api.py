import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from furance_shared.protocol.http_schema import ApiResponse
from app.main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_sampler_api_structure(client):
    # Just test that the endpoints exist
    with patch("app.api.sampler.SamplerService") as mock_sampler_service_class:
        mock_sampler_service = AsyncMock()
        mock_sampler_service.start.return_value = ApiResponse(code=0)
        mock_sampler_service.stop.return_value = ApiResponse(code=0)
        mock_sampler_service.query.return_value = ApiResponse(code=0, data={"status": "idle"})
        mock_sampler_service_class.return_value = mock_sampler_service

        # Test start
        resp = await client.post("/api/v1/dispatch/sampler/command", json={"command": "start", "params": {}})
        assert resp.status_code == 200

        # Test query
        resp = await client.get("/api/v1/dispatch/sampler/status")
        assert resp.status_code == 200