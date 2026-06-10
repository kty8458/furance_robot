from typing import Optional
from pydantic import BaseModel, Field, model_validator
from furance_shared.models.robot import ArmSide


class TeachPreset(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    joint_angles: list[float] = Field(min_length=7, max_length=14)
    joint_angles_right: Optional[list[float]] = Field(default=None, min_length=7, max_length=7)
    end_effector: dict = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0})
    coordinate_frame: str = "base_link"
    method: str = "moveJ"

    @model_validator(mode="after")
    def validate_joint_angles(self):
        if self.arm == ArmSide.BOTH:
            if len(self.joint_angles) != 14 and not self.joint_angles_right:
                raise ValueError("both-arm preset requires 14 joint_angles or 7+7 joint_angles+joint_angles_right")
        else:
            if len(self.joint_angles) != 7:
                raise ValueError("single-arm preset requires 7 joint_angles")
        return self


class TeachPresetSummary(BaseModel):
    arm: ArmSide
    name: str
    coordinate_frame: str = "base_link"
