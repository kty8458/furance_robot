from fastapi import APIRouter, HTTPException, Request
from furance_shared.models.command import ArmMoveCommand, TeachSaveCommand, TeachExecCommand
from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.utils.errors import FuranceError
from app.services.arm_service import ArmService
from app.models.teach import TeachPreset
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/robot/{robot_id}/arm", tags=["arm"])

def _get_arm_service(request: Request) -> ArmService:
    settings = get_settings()
    return ArmService(
        ros2_client=request.app.state.ros2.service_client,
        teach_dir=settings.teach_data_dir,
    )


@router.post("/move", response_model=ApiResponse)
async def arm_move(robot_id: str, cmd: ArmMoveCommand, request: Request):
    return await _get_arm_service(request).arm_move(robot_id, cmd)


@router.post("/teach/save", response_model=ApiResponse)
async def teach_save(robot_id: str, cmd: TeachSaveCommand, request: Request):
    try:
        _get_arm_service(request).save_teach(robot_id, TeachPreset(
            arm=cmd.arm, name=cmd.name, joint_angles=[0.0] * 7
        ))
        return ApiResponse(data={"name": cmd.name})
    except FuranceError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())


@router.get("/teach/list", response_model=ApiResponse)
async def teach_list(robot_id: str, request: Request):
    presets = _get_arm_service(request).list_teach(robot_id)
    return ApiResponse(data=[p.model_dump() for p in presets])


@router.post("/teach/exec", response_model=ApiResponse)
async def teach_exec(robot_id: str, cmd: TeachExecCommand, request: Request):
    try:
        return await _get_arm_service(request).exec_teach(robot_id, cmd)
    except FuranceError as e:
        raise HTTPException(status_code=404, detail=e.to_dict())


@router.delete("/teach/{name}", response_model=ApiResponse)
async def teach_delete(robot_id: str, name: str, request: Request):
    _get_arm_service(request).delete_teach(robot_id, name)
    return ApiResponse(data={"deleted": name})
