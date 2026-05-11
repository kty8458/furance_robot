import tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from app.ros2.service_client import MockRos2ServiceClient
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/robot/{robot_id}/arm", tags=["arm"])

# Use temp directory for testing
_temp_dir = tempfile.mkdtemp()
_settings = get_settings()
_arm_service = ArmService(
    ros2_client=MockRos2ServiceClient(),
    teach_dir=str(Path(_temp_dir) / "teach"),
)


@router.post("/move", response_model=ApiResponse)
async def arm_move(robot_id: str, cmd: ArmMoveCommand):
    return await _arm_service.arm_move(robot_id, cmd)


@router.post("/teach/save", response_model=ApiResponse)
async def teach_save(robot_id: str, cmd: TeachSaveCommand):
    try:
        _arm_service.save_teach(robot_id, TeachPreset(
            arm=cmd.arm, name=cmd.name, joint_angles=[0.0] * 7
        ))
        return ApiResponse(data={"name": cmd.name})
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())


@router.get("/teach/list", response_model=ApiResponse)
async def teach_list(robot_id: str):
    presets = _arm_service.list_teach(robot_id)
    return ApiResponse(data=[p.model_dump() for p in presets])


@router.post("/teach/exec", response_model=ApiResponse)
async def teach_exec(robot_id: str, cmd: TeachExecCommand):
    try:
        return await _arm_service.exec_teach(robot_id, cmd)
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.delete("/teach/{name}", response_model=ApiResponse)
async def teach_delete(robot_id: str, name: str):
    _arm_service.delete_teach(robot_id, name)
    return ApiResponse(data={"deleted": name})
