import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def mock_ros2_client():
    client = AsyncMock()
    client.call_service = AsyncMock(return_value={"success": True, "message": "ok"})
    return client
