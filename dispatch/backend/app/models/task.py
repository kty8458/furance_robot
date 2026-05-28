from pydantic import BaseModel, Field
from furance_shared.utils.enum import StrEnum
from typing import Literal, Optional


class TaskStepType(StrEnum):
    WORKFLOW = "workflow"
    SAMPLER = "sampler"
    DELAY = "delay"


class WorkflowStepConfig(BaseModel):
    robot_id: str
    workflow_name: str


class SamplerStepConfig(BaseModel):
    command: str
    params: dict = {}


class DelayStepConfig(BaseModel):
    seconds: float = Field(gt=0, default=1.0)


class TaskStep(BaseModel):
    id: str = Field(min_length=1)
    type: TaskStepType
    label: str = ""
    config: dict = {}


class TaskTemplate(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    steps: list[TaskStep] = []
    version: int = 1
