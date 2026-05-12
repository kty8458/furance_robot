from furance_shared.utils.enum import StrEnum
from typing import Dict, Optional

from pydantic import BaseModel

from furance_shared.models.robot import ArmState, GripperInfo, Position


class WsFrameType(StrEnum):
    STATUS = "status"
    ERROR = "error"
    LOG = "log"


class StatusPayload(BaseModel):
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
    ros2_nodes: Optional[Dict[str, str]] = None


class ErrorPayload(BaseModel):
    error_code: int
    error_msg: str
    source: str


class LogPayload(BaseModel):
    level: str
    source: str
    node: str = ""
    message: str


class WsFrame(BaseModel):
    type: WsFrameType
    robot_id: str
    timestamp: Optional[int] = None
    payload: BaseModel


class StatusFrame(BaseModel):
    type: WsFrameType = WsFrameType.STATUS
    robot_id: str
    timestamp: Optional[int] = None
    payload: StatusPayload


class ErrorFrame(BaseModel):
    type: WsFrameType = WsFrameType.ERROR
    robot_id: str
    timestamp: Optional[int] = None
    payload: ErrorPayload


class LogFrame(BaseModel):
    type: WsFrameType = WsFrameType.LOG
    robot_id: str
    timestamp: Optional[int] = None
    payload: LogPayload
