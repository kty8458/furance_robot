from typing import Optional
import logging

from fastapi import APIRouter, HTTPException, Request
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/robot/{robot_id}/arm", tags=["arm"])

def _get_arm_service(request: Request) -> ArmService:
    settings = get_settings()
    moveit_client = getattr(request.app.state.ros2, 'moveit_client', None)
    return ArmService(
        ros2_client=request.app.state.ros2.service_client,
        moveit_client=moveit_client,
        teach_dir=settings.teach_data_dir,
    )


def _get_current_arm_state(request: Request, robot_id: str, arm: str) -> dict:
    status_service = request.app.state.status_service
    latest = status_service.get_latest(robot_id)
    if not latest:
        return {}
    return latest.get("arm", {}).get(arm.value if hasattr(arm, 'value') else arm, {})


@router.post("/move", response_model=ApiResponse)
async def arm_move(robot_id: str, cmd: ArmMoveCommand, request: Request):
    return await _get_arm_service(request).arm_move(robot_id, cmd)


@router.post("/teach/save", response_model=ApiResponse)
async def teach_save(robot_id: str, cmd: TeachSaveCommand, request: Request, workflow: Optional[str] = None):
    try:
        side_data = _get_current_arm_state(request, robot_id, cmd.arm)
        joint_angles = side_data.get("joint_angles", [0.0] * 7)
        end_effector = side_data.get("end_effector", {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0})
        coordinate_frame = side_data.get("coordinate_frame", "base_link")

        _get_arm_service(request).save_teach(robot_id, TeachPreset(
            arm=cmd.arm, name=cmd.name, joint_angles=joint_angles,
            end_effector=end_effector, coordinate_frame=coordinate_frame,
            method=cmd.method,
        ), workflow_name=workflow)
        return ApiResponse(data={"name": cmd.name})
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
    except ValueError as e:
        return ApiResponse(code=1001, message=str(e))
    except Exception as e:
        logger.exception("teach_save failed")
        return ApiResponse(code=500, message=str(e))


@router.put("/teach/{name}", response_model=ApiResponse)
async def teach_update(robot_id: str, name: str, cmd: TeachSaveCommand, request: Request, workflow: Optional[str] = None):
    try:
        side_data = _get_current_arm_state(request, robot_id, cmd.arm)
        joint_angles = side_data.get("joint_angles", [0.0] * 7)
        end_effector = side_data.get("end_effector", {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0})
        coordinate_frame = side_data.get("coordinate_frame", "base_link")

        _get_arm_service(request).save_teach(robot_id, TeachPreset(
            arm=cmd.arm, name=name, joint_angles=joint_angles,
            end_effector=end_effector, coordinate_frame=coordinate_frame,
            method=cmd.method,
        ), overwrite=True, workflow_name=workflow)
        return ApiResponse(data={"name": name})
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())


@router.get("/teach/list", response_model=ApiResponse)
async def teach_list(robot_id: str, request: Request, workflow: Optional[str] = None):
    presets = _get_arm_service(request).list_teach(robot_id, workflow_name=workflow)
    return ApiResponse(data=[p.model_dump() for p in presets])


@router.post("/teach/exec", response_model=ApiResponse)
async def teach_exec(robot_id: str, cmd: TeachExecCommand, request: Request, workflow: Optional[str] = None):
    try:
        return await _get_arm_service(request).exec_teach(robot_id, cmd, workflow_name=workflow)
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.delete("/teach/{name}", response_model=ApiResponse)
async def teach_delete(robot_id: str, name: str, request: Request, workflow: Optional[str] = None):
    _get_arm_service(request).delete_teach(robot_id, name, workflow_name=workflow)
    return ApiResponse(data={"deleted": name})


@router.get("/teach/ros2", response_model=ApiResponse)
async def teach_ros2_list(robot_id: str, request: Request, arm: Optional[str] = None):
    """Query teach points via ROS2 /GetTeachPoints service."""
    from app.services.robot_service import _check_result
    ros2_client = request.app.state.ros2.service_client
    params = {"robot_id": robot_id}
    if arm:
        params["arm"] = arm
    result = await ros2_client.call_service("/GetTeachPoints", params)
    return _check_result(result)


@router.post("/teach/compose", response_model=ApiResponse)
async def teach_compose(robot_id: str, request: Request):
    """Combine two single-arm moveJ presets into a dual-arm both preset.

    Request body: { left_name, right_name, composed_name, overwrite? }
    """
    try:
        from pydantic import BaseModel, Field
        class ComposeRequest(BaseModel):
            left_name: str = Field(min_length=1)
            right_name: str = Field(min_length=1)
            composed_name: str = Field(min_length=1)
            overwrite: bool = False

        body = ComposeRequest(**await request.json())
        preset = _get_arm_service(request).compose_teach(
            robot_id, body.left_name, body.right_name, body.composed_name, body.overwrite,
        )
        return ApiResponse(data=preset.model_dump())
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
