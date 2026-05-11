import pytest


@pytest.mark.asyncio
async def test_arm_move_movej(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/arm/move",
        json={
            "arm": "left",
            "method": "moveJ",
            "joint_angles": [0.0] * 7,
            "coordinate": "base_link",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0


@pytest.mark.asyncio
async def test_arm_teach_save_and_list(client):
    resp = await client.post(
        "/api/v1/robot/robot_001/arm/teach/save",
        json={"arm": "left", "name": "test_preset"},
    )
    assert resp.status_code == 200

    resp = await client.get("/api/v1/robot/robot_001/arm/teach/list")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]) >= 1
