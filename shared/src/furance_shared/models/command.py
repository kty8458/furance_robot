from furance_shared.utils.enum import StrEnum
from typing import Dict, Optional

from pydantic import BaseModel, Field, model_validator

from furance_shared.models.robot import ArmSide, GripperAction, LiftDirection, ChargeAction


class ArmMoveMethod(StrEnum):
    MOVEP = "movep"
    MOVEL = "moveL"
    MOVEJ = "moveJ"


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
    joint_angles_right: Optional[list[float]] = Field(default=None, min_length=7, max_length=7)
    position: Optional[Dict[str, float]] = None
    coordinate: str = "base_link"

    @model_validator(mode="after")
    def validate_method_params(self):
        if self.method in (ArmMoveMethod.MOVEP, ArmMoveMethod.MOVEL):
            if self.position is None:
                raise ValueError(f"{self.method} requires position")
        if self.method == ArmMoveMethod.MOVEJ:
            if self.arm != ArmSide.BOTH and self.joint_angles is None:
                raise ValueError("moveJ requires joint_angles")
            if self.arm == ArmSide.BOTH and (self.joint_angles is None or self.joint_angles_right is None):
                raise ValueError("moveJ both requires joint_angles + joint_angles_right")
        return self


class TeachSaveCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    method: ArmMoveMethod = ArmMoveMethod.MOVEJ


class TeachExecCommand(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    method: Optional[ArmMoveMethod] = None


class WaistControlCommand(BaseModel):
    waist_angle: float = Field(ge=0, le=600)
    waist_speed: float = Field(default=20.0, gt=0)
    reserve: float = 0.0


class AscendControlCommand(BaseModel):
    ascend_pos: float
    ascend_speed: float = Field(default=20.0, gt=0)
    reserve: float = 0.0


class HeadControlCommand(BaseModel):
    head_angle: float = Field(ge=0, le=35)
    head_speed: float = Field(default=10.0, gt=0)
    reserve: float = 0.0
