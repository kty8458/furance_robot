from pydantic import BaseModel, Field
from furance_shared.models.robot import ArmSide


class TeachPreset(BaseModel):
    arm: ArmSide
    name: str = Field(min_length=1, max_length=64)
    joint_angles: list[float] = Field(min_length=7, max_length=7)


class TeachPresetSummary(BaseModel):
    arm: ArmSide
    name: str
