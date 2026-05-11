from fastapi import APIRouter
from furance_shared.models.command import (
    MoveCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/robot/{robot_id}", tags=["robot"])

_proxy = RobotProxyService()


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/home")


@router.post("/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/move", cmd.model_dump())


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/grab", cmd.model_dump())


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/place", cmd.model_dump())


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/gripper", cmd.model_dump())


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/lift", cmd.model_dump())


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/charge", cmd.model_dump())


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/enable", cmd.model_dump())


@router.get("/status", response_model=ApiResponse)
async def status(robot_id: str):
    return await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")


@router.get("", response_model=ApiResponse)
async def list_robots():
    from app.core.config import get_settings
    settings = get_settings()
    return ApiResponse(data=[r.model_dump() for r in settings.robots])