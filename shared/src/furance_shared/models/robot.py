from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from furance_shared.utils.enum import StrEnum


class ArmSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"


class GripperAction(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    POSITION = "position"
    CLEAR_ERROR = "clear_error"


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
    state: str = "unknown"
    force: float = 0.0
    torque: float = 0.0
    distance: float = 0.0
    temperature: float = 0.0
    connected: bool = False
    # EtherCAT 夹爪扩展字段
    claw_status: int = 0
    claw_status_text: str = ""
    claw_error: int = 0
    motor_error: int = 0
    current_width_mm: float = 0.0
    bus_voltage_v: float = 0.0
    driver_temperature_c: float = 0.0
    online: bool = False
    has_error: bool = False


class EndEffectorPose(BaseModel):
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0


class JointState(BaseModel):
    robot_id: str
    joints: List[float] = Field(default_factory=list)
    timestamp: Optional[str] = None


class ArmState(BaseModel):
    joint_angles: list[float] = Field(min_length=7, max_length=7)
    end_effector: EndEffectorPose = EndEffectorPose()
    coordinate_frame: str = "base_link"
    status: str = "idle"
    error_code: int = 0


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
