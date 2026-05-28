from typing import Literal, Optional
from pydantic import BaseModel, Field

StepType = Literal["move", "upper_limb", "upper_body", "gripper", "vision", "sleep"]


class MoveStepConfig(BaseModel):
    mode: Literal["point", "path"] = "point"


class UpperLimbStepConfig(BaseModel):
    mode: Literal["preset", "pose"] = "preset"
    arm: str = "left"
    preset_name: Optional[str] = None
    method: str = "moveJ"
    reference_frame: Optional[str] = None
    position: Optional[dict] = None


class UpperBodyStepConfig(BaseModel):
    waist_angle: Optional[float] = None
    waist_speed: float = 20.0
    ascend_pos: Optional[float] = None
    ascend_speed: float = 20.0
    head_angle: Optional[float] = None
    head_speed: float = 10.0


class GripperStepConfig(BaseModel):
    arm: str = "left"
    action: str = "open"
    force: float = 0.0


class VisionStepConfig(BaseModel):
    scene: str = ""
    camera_id: str = "camera_1"


class SleepStepConfig(BaseModel):
    duration: float = Field(gt=0, default=1.0)


class WorkflowStep(BaseModel):
    id: str = Field(min_length=1)
    type: StepType
    label: str = ""
    config: dict = {}


class Workflow(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = ""
    steps: list[WorkflowStep] = []
    version: int = 1


class NavPointParam(BaseModel):
    step_id: str
    map_name: str = ""
    point_name: Optional[str] = None
    path_name: Optional[str] = None
    path_type: str = "NavigationPointTask"


class WorkflowExecuteRequest(BaseModel):
    nav_params: list[NavPointParam] = []


class StepResult(BaseModel):
    step_id: str
    success: bool
    message: str = ""
    data: dict = {}


class WorkflowExecuteResponse(BaseModel):
    execution_id: str = ""
    status: Literal["started", "running", "completed", "failed", "cancelled"] = "started"
    success: bool = True
    message: str = ""
    step_results: list[StepResult] = []
    error_step_id: Optional[str] = None
