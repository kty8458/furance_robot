import pytest


@pytest.mark.asyncio
async def test_home_command(client):
    resp = await client.post("/api/v1/robot/robot_001/home")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_grab_command(client):
    resp = await client.post("/api/v1/robot/robot_001/grab", json={"target": "sample_pos"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0


@pytest.mark.asyncio
async def test_place_command(client):
    resp = await client.post("/api/v1/robot/robot_001/place", json={"target": "output_pos"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_gripper_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/gripper",
        json={"arm": "left", "action": "close", "force": 50.0},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_lift_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/lift",
        json={"direction": "up", "height": 1.5},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_charge_command(client):
    resp = await client.post("/api/v1/robot/robot_001/charge", json={"action": "start"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_enable_command(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/enable",
        json={"enable": True, "clear_error": True},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_invalid_params(client):
    resp = await client.post("/api/v1/robot/robot_001/gripper", json={"arm": "invalid"})
    assert resp.status_code == 422
