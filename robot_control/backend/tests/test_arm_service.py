import pytest
from unittest.mock import AsyncMock
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from app.ros2.moveit_client import MockMoveItServiceClient
from furance_shared.models.robot import ArmSide
from furance_shared.models.command import ArmMoveCommand, ArmMoveMethod


@pytest.fixture
def arm_service(tmp_path):
    return ArmService(teach_dir=str(tmp_path))


@pytest.fixture
def arm_service_with_moveit(tmp_path):
    return ArmService(
        moveit_client=MockMoveItServiceClient(),
        teach_dir=str(tmp_path),
    )


def test_save_and_list_teach(arm_service):
    preset = TeachPreset(
        arm=ArmSide.LEFT, name="grab_pos", joint_angles=[0.0] * 7
    )
    arm_service.save_teach("robot_001", preset)
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 1
    assert presets[0].name == "grab_pos"
    assert presets[0].arm == "left"


def test_list_teach_empty(arm_service):
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 0


def test_delete_teach(arm_service):
    preset = TeachPreset(
        arm=ArmSide.LEFT, name="grab_pos", joint_angles=[0.0] * 7
    )
    arm_service.save_teach("robot_001", preset)
    arm_service.delete_teach("robot_001", "grab_pos")
    presets = arm_service.list_teach("robot_001")
    assert len(presets) == 0


def test_delete_nonexistent_teach(arm_service):
    arm_service.delete_teach("robot_001", "nonexistent")
    # should not raise


@pytest.mark.asyncio
async def test_arm_move_movej_via_moveit(arm_service_with_moveit):
    cmd = ArmMoveCommand(
        arm=ArmSide.LEFT, method=ArmMoveMethod.MOVEJ,
        joint_angles=[0.0] * 7, coordinate="base_link",
    )
    resp = await arm_service_with_moveit.arm_move("robot_001", cmd)
    assert resp.code == 0
    assert resp.data["success"] is True


@pytest.mark.asyncio
async def test_arm_move_movep_via_moveit(arm_service_with_moveit):
    cmd = ArmMoveCommand(
        arm=ArmSide.RIGHT, method=ArmMoveMethod.MOVEP,
        position={"x": 0.3, "y": -0.1, "z": 0.4, "qw": 1.0},
        coordinate="base_link",
    )
    resp = await arm_service_with_moveit.arm_move("robot_001", cmd)
    assert resp.code == 0
    assert resp.data["success"] is True


@pytest.mark.asyncio
async def test_arm_move_movel_via_moveit(arm_service_with_moveit):
    cmd = ArmMoveCommand(
        arm=ArmSide.LEFT, method=ArmMoveMethod.MOVEL,
        position={"x": 0.2, "y": 0.0, "z": 0.3, "qw": 1.0},
        coordinate="base_link",
    )
    resp = await arm_service_with_moveit.arm_move("robot_001", cmd)
    assert resp.code == 0
    assert resp.data["success"] is True


@pytest.mark.asyncio
async def test_arm_move_movej_failure_returns_error(tmp_path):
    failing = AsyncMock()
    failing.move_j = AsyncMock(return_value={"success": False, "message": "planning failed"})
    svc = ArmService(moveit_client=failing, teach_dir=str(tmp_path))
    cmd = ArmMoveCommand(
        arm=ArmSide.LEFT, method=ArmMoveMethod.MOVEJ,
        joint_angles=[0.0] * 7, coordinate="base_link",
    )
    resp = await svc.arm_move("robot_001", cmd)
    assert resp.code == 1001
    assert "planning failed" in resp.message
    failing.move_j.assert_awaited_once_with(lor="left", joint_positions=[0.0] * 7)
