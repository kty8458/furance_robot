from fastapi import APIRouter, Request
from furance_shared.models.command import (
    GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_service import RobotService

router = APIRouter(prefix="/api/v1/robot/{robot_id}", tags=["robot"])


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.home(robot_id)


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.grab(robot_id, cmd)


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.place(robot_id, cmd)


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.gripper(robot_id, cmd)


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.lift(robot_id, cmd)


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.charge(robot_id, cmd)


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand, request: Request):
    service = RobotService(request.app.state.ros2.service_client)
    return await service.enable(robot_id, cmd)
