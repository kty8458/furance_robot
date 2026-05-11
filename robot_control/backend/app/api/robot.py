from fastapi import APIRouter, Depends
from furance_shared.models.command import (
    GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_service import RobotService
from app.ros2.service_client import MockRos2ServiceClient

router = APIRouter(prefix="/api/v1/robot/{robot_id}", tags=["robot"])

_ros2_client = MockRos2ServiceClient()
_robot_service = RobotService(_ros2_client)


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str):
    return await _robot_service.home(robot_id)


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand):
    return await _robot_service.grab(robot_id, cmd)


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand):
    return await _robot_service.place(robot_id, cmd)


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand):
    return await _robot_service.gripper(robot_id, cmd)


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand):
    return await _robot_service.lift(robot_id, cmd)


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand):
    return await _robot_service.charge(robot_id, cmd)


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand):
    return await _robot_service.enable(robot_id, cmd)
