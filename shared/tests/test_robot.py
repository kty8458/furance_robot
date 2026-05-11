from furance_shared.models.robot import (
    ArmSide, GripperAction, GripperState, LiftDirection, ChargeAction,
    Position, GripperInfo, ArmState, RobotStatus,
)


def test_arm_side_values():
    assert ArmSide.LEFT == "left"
    assert ArmSide.RIGHT == "right"


def test_gripper_action_values():
    assert GripperAction.OPEN == "open"
    assert GripperAction.CLOSE == "close"


def test_gripper_state_values():
    assert GripperState.OPEN == "open"
    assert GripperState.CLOSED == "closed"


def test_lift_direction_values():
    assert LiftDirection.UP == "up"
    assert LiftDirection.DOWN == "down"


def test_charge_action_values():
    assert ChargeAction.START == "start"
    assert ChargeAction.STOP == "stop"


def test_position():
    pos = Position(x=1.0, y=2.0, theta=0.5)
    assert pos.x == 1.0
    assert pos.y == 2.0
    assert pos.theta == 0.5


def test_gripper_info():
    info = GripperInfo(state=GripperState.OPEN, force=50.0)
    assert info.state == "open"
    assert info.force == 50.0


def test_arm_state():
    arm = ArmState(joint_angles=[0.0] * 7, status="idle")
    assert len(arm.joint_angles) == 7
    assert arm.status == "idle"


def test_robot_status():
    status = RobotStatus(
        position=Position(x=1.0, y=2.0, theta=0.5),
        current_map="map_001",
        lift_height=0.3,
        gripper={
            "left": GripperInfo(state=GripperState.OPEN, force=0.0),
            "right": GripperInfo(state=GripperState.CLOSED, force=50.0),
        },
        battery=85,
        charging=False,
        enabled=True,
        error_code=0,
        task_status="idle",
        arm={
            "left": ArmState(joint_angles=[0.0] * 7, status="idle"),
            "right": ArmState(joint_angles=[0.0] * 7, status="idle"),
        },
    )
    assert status.battery == 85
    assert status.gripper["left"].state == "open"
    assert status.arm["right"].status == "idle"
