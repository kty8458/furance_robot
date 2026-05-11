from furance_shared.protocol.ws_frames import (
    WsFrameType, StatusPayload, ErrorPayload, LogPayload,
    StatusFrame, ErrorFrame, LogFrame,
)
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState


def test_status_frame():
    frame = StatusFrame(
        robot_id="robot_001",
        payload=StatusPayload(
            position=Position(x=1.0, y=2.0, theta=0.5),
            current_map="map_001",
            gripper={
                "left": GripperInfo(state=GripperState.OPEN, force=0.0),
                "right": GripperInfo(state=GripperState.CLOSED, force=50.0),
            },
            arm={
                "left": ArmState(joint_angles=[0.0] * 7, status="idle"),
                "right": ArmState(joint_angles=[0.0] * 7, status="idle"),
            },
        ),
    )
    assert frame.type == WsFrameType.STATUS
    assert frame.robot_id == "robot_001"
    assert frame.payload.battery == 0


def test_error_frame():
    frame = ErrorFrame(
        robot_id="robot_001",
        payload=ErrorPayload(error_code=2001, error_msg="Move failed", source="move_node"),
    )
    assert frame.type == WsFrameType.ERROR
    assert frame.payload.error_code == 2001


def test_log_frame():
    frame = LogFrame(
        robot_id="robot_001",
        payload=LogPayload(level="info", source="move_node", message="Navigation goal reached"),
    )
    assert frame.type == WsFrameType.LOG
    assert frame.payload.level == "info"


def test_frame_serialization():
    frame = ErrorFrame(
        robot_id="robot_001",
        payload=ErrorPayload(error_code=1001, error_msg="timeout", source="ros2"),
    )
    data = frame.model_dump()
    assert data["type"] == "error"
    assert data["payload"]["error_code"] == 1001
