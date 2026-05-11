import pytest
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from furance_shared.models.robot import ArmSide


@pytest.fixture
def arm_service(tmp_path):
    return ArmService(teach_dir=str(tmp_path))


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
