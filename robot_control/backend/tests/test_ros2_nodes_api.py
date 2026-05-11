import pytest


@pytest.mark.asyncio
async def test_list_nodes(client):
    resp = await client.get("/api/v1/ros2/nodes")
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_start_node(client):
    resp = await client.post("/api/v1/ros2/nodes/move_node/start")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stop_node(client):
    resp = await client.post("/api/v1/ros2/nodes/move_node/stop")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_node_status(client):
    resp = await client.get("/api/v1/ros2/nodes/move_node/status")
    assert resp.status_code == 200
