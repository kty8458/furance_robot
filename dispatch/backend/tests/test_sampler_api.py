import pytest
from unittest.mock import AsyncMock, patch
from furance_shared.protocol.http_schema import ApiResponse


@pytest.mark.asyncio
async def test_sampler_api_structure(client):
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
