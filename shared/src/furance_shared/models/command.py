from furance_shared.utils.enum import StrEnum
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator

from furance_shared.models.robot import ArmSide, GripperAction, LiftDirection, ChargeAction


class ArmMoveMethod(StrEnum):
    MOVEP = "movep"
    MOVEL = "moveL"
    MOVEJ = "moveJ"


class MoveCommand(BaseModel):
    map_id: str
    waypoint_id: str
    speed: float = Field(gt=0, le=2.0)


class GrabCommand(BaseModel):
    target: str


class PlaceCommand(BaseModel):
    target: str


class GripperCommand(BaseModel):
    arm: ArmSide
    action: GripperAction
    force: float = Field(default=0.0, ge=0)


class LiftCommand(BaseModel):
    direction: LiftDirection
    height: float = Field(gt=0)


class ChargeCommand(BaseModel):
    action: ChargeAction


class EnableCommand(BaseModel):
    enable: bool
    clear_error: bool


class HomeCommand(BaseModel):
    pass


class ArmMoveCommand(BaseModel):
    arm: ArmSide
    method: ArmMoveMethod
    joint_angles: Optional[list[float]] = Field(default=None, min_length=7, max_length=7)
    position: Optional[Dict[str, float]] = None
    coordinate: str = "base_link"

    @model_validator(mode="after")
    def validate_method_params(self):
        if self.method in (ArmMoveMethod.MOVEP, ArmMoveMethod.MOVEL):
            if self.position is None:
                raise ValueError(f"{self.method} requires position")
        if self.method == ArmMoveMethod.MOVEJ:
            if self.joint_angles is None:
                raise ValueError("moveJ requires joint_angles")
        return self


class TeachSaveCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)


class TeachExecCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
