from furance_shared.models.command import (
    GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand, HomeCommand,
    ArmMoveCommand, ArmMoveMethod, TeachSaveCommand, TeachExecCommand,
)


def test_grab_command():
    cmd = GrabCommand(target="sample_pos")
    assert cmd.target == "sample_pos"


def test_place_command():
    cmd = PlaceCommand(target="sampler_input")
    assert cmd.target == "sampler_input"


def test_gripper_command_with_force():
    cmd = GripperCommand(arm="left", action="close", force=50.0)
    assert cmd.arm == "left"
    assert cmd.force == 50.0


def test_gripper_command_without_force():
    cmd = GripperCommand(arm="right", action="open")
    assert cmd.force == 0.0


def test_lift_command():
    cmd = LiftCommand(direction="up", height=1.5)
    assert cmd.direction == "up"
    assert cmd.height == 1.5


def test_charge_command():
    cmd = ChargeCommand(action="start")
    assert cmd.action == "start"


def test_enable_command():
    cmd = EnableCommand(enable=True, clear_error=True)
    assert cmd.enable is True


def test_home_command():
    cmd = HomeCommand()
    assert isinstance(cmd, HomeCommand)


def test_arm_move_command_movej():
    cmd = ArmMoveCommand(
        arm="left", method=ArmMoveMethod.MOVEJ,
        joint_angles=[0.0] * 7, coordinate="base_link",
    )
    assert cmd.method == "moveJ"
    assert cmd.position is None


def test_arm_move_command_movep():
    cmd = ArmMoveCommand(
        arm="right", method=ArmMoveMethod.MOVEP,
        position={"x": 0.1, "y": 0.2, "z": 0.3, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
        coordinate="base_link",
    )
    assert cmd.joint_angles is None


def test_teach_save_command():
    cmd = TeachSaveCommand(arm="left", name="grab_pos")
    assert cmd.name == "grab_pos"


def test_teach_exec_command():
    cmd = TeachExecCommand(arm="left", name="grab_pos")
    assert cmd.name == "grab_pos"
