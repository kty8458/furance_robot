import pytest
from httpx import AsyncClient, ASGITransport
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
async def test_get_maps(client):
    resp = await client.get("/api/v1/maps")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_get_waypoints(client):
    resp = await client.get("/api/v1/maps/map_001/waypoints")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_move_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/move",
        json={"map_id": "map_001", "waypoint_id": "wp_01", "speed": 0.5},
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
