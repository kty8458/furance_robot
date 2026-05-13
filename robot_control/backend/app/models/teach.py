from typing import Optional
from pydantic import BaseModel, Field
from furance_shared.models.robot import ArmSide


class TeachPreset(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    joint_angles: list[float] = Field(min_length=7, max_length=7)
    end_effector: dict = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0})
    coordinate_frame: str = "base_link"


class TeachPresetSummary(BaseModel):
    arm: ArmSide
    name: str
    coordinate_frame: str = "base_link"
