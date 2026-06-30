from typing import Literal, Optional
from pydantic import BaseModel, Field

StepType = Literal["move", "upper_limb", "upper_body", "gripper", "vision", "sleep"]


class MoveStepConfig(BaseModel):
    # 运动模式: scheduler (调度系统) / manual (手动) / move_with_params (定距离/定角度)
    move_source: str = "scheduler"
    mode: Literal["point", "path"] = "point"
    map_name: Optional[str] = None
    point_name: Optional[str] = None
    path_name: Optional[str] = None
    path_type: str = "NavigationPointTask"
    # 定距离/定角度移动参数
    mwp_mode: int = 1                  # 1=定距离, 2=定角度
    linear_velocity: float = 0.2
    slip_angle: float = 0.0
    angular_velocity: float = 0.2
    target_distance: float = 1.0
    target_angle: float = 0.0


class UpperLimbStepConfig(BaseModel):
    mode: Literal["preset", "pose"] = "preset"
    arm: str = "left"
    preset_name: Optional[str] = None
    left_preset_name: Optional[str] = None
    right_preset_name: Optional[str] = None
    method: str = "moveJ"
    use_combined: bool = True   # True=combine into one both_arm trajectory; False=execute left then right
    use_composed_preset: bool = False  # True=use pre-composed both-arm preset; False=combine two single-arm presets
    reference_frame: Optional[str] = None
    left_reference_frame: Optional[str] = None
    right_reference_frame: Optional[str] = None
    position: Optional[dict] = None
    left_position: Optional[dict] = None
    right_position: Optional[dict] = None
    vision_source: Optional[str] = None
    left_vision_source: Optional[str] = None
    right_vision_source: Optional[str] = None
    # pose 模式的来源 + 偏移
    pose_mode: str = "manual"          # manual / current_ee / vision
    vision_step_label: Optional[str] = None
    enable_offset: bool = False
    offset_ref_base: bool = True       # base_link 坐标系下做偏移
    offset_ref_tool: bool = False      # tool_link 坐标系下做偏移
    offset: Optional[dict] = None      # {x, y, z, roll, pitch, yaw}, 单位 mm/deg


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
    force: float = 0.0       # 0-100 torque %
    position: float = 0.0    # 0-100 position %


class VisionStepConfig(BaseModel):
    camera_id: str = ""
    function: str = "qr_detect"    # qr_detect / vision_model
    scene: str = ""               # scene_id
    point_name: str = ""          # 标定点名称


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
    manual_mode: bool = False   # 手动模式: 每步等待 trigger_next_step


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
