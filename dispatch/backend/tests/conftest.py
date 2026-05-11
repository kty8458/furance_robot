import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from furance_shared.protocol.http_schema import ApiResponse


@pytest.fixture
def mock_robot_proxy():
    proxy = AsyncMock()
    proxy.forward = AsyncMock(return_value=ApiResponse(code=0, data={"success": True}))
    proxy.forward_get = AsyncMock(return_value=ApiResponse(code=0, data={}))
    return proxy