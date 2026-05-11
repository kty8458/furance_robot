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
async def test_robot_home(client, mock_robot_proxy):
    with patch("app.api.robot._proxy", mock_robot_proxy):
        resp = await client.post("/api/v1/robot/robot_001/home")
        assert resp.status_code == 200
        assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_robot_move(client, mock_robot_proxy):
    with patch("app.api.robot._proxy", mock_robot_proxy):
        resp = await client.post(
            "/api/v1/robot/robot_001/move",
            json={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_grab(client, mock_robot_proxy):
    with patch("app.api.robot._proxy", mock_robot_proxy):
        resp = await client.post(
            "/api/v1/robot/robot_001/grab",
            json={"target": "sample"},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_status(client, mock_robot_proxy):
    with patch("app.api.robot._proxy", mock_robot_proxy):
        resp = await client.get("/api/v1/robot/robot_001/status")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_robot_not_found(client):
    from app.services.robot_proxy import RobotProxyService
    with patch.object(RobotProxyService, "forward") as mock_forward:
        mock_forward.return_value = ApiResponse(code=3002, message="Robot not found")
        resp = await client.post("/api/v1/robot/robot_999/home")
        assert resp.status_code == 200
        assert resp.json()["code"] == 3002