from furance_shared.utils.enum import StrEnum
from typing import Dict

from pydantic import BaseModel, Field


class ArmSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class GripperAction(StrEnum):
    OPEN = "open"
    CLOSE = "close"


class GripperState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class LiftDirection(StrEnum):
    UP = "up"
    DOWN = "down"


class ChargeAction(StrEnum):
    START = "start"
    STOP = "stop"


class Position(BaseModel):
    x: float
    y: float
    theta: float


class GripperInfo(BaseModel):
    state: GripperState
    force: float = 0.0


class EndEffectorPose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class ArmState(BaseModel):
    joint_angles: list[float] = Field(min_length=7, max_length=7)
    end_effector: EndEffectorPose = EndEffectorPose()
    coordinate_frame: str = "base_link"
    status: str = "idle"


class RobotStatus(BaseModel):
    position: Position
    current_map: str = ""
    lift_height: float = 0.0
    gripper: Dict[str, GripperInfo]
    battery: int = 0
    charging: bool = False
    enabled: bool = False
    error_code: int = 0
    task_status: str = "idle"
    arm: Dict[str, ArmState]
