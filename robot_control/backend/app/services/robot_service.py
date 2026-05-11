from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.models.command import (
    HomeCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from app.ros2.service_client import Ros2ServiceClientBase


ROS2_SERVICE_MAP = {
    "home": "/HomeCommand",
    "grab": "/GrabCommand",
    "place": "/PlaceCommand",
    "gripper": "/GripperCommand",
    "lift": "/LiftCommand",
    "charge": "/ChargeCommand",
    "enable": "/EnableCommand",
}


class RobotService:
    def __init__(self, ros2_client: Ros2ServiceClientBase):
        self._ros2 = ros2_client

    async def home(self, robot_id: str) -> ApiResponse:
        result = await self._ros2.call_service("/HomeCommand", {})
        return ApiResponse(data=result)

    async def grab(self, robot_id: str, cmd: GrabCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GrabCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def place(self, robot_id: str, cmd: PlaceCommand) -> ApiResponse:
        result = await self._ros2.call_service("/PlaceCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def gripper(self, robot_id: str, cmd: GripperCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def lift(self, robot_id: str, cmd: LiftCommand) -> ApiResponse:
        result = await self._ros2.call_service("/LiftCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def charge(self, robot_id: str, cmd: ChargeCommand) -> ApiResponse:
        result = await self._ros2.call_service("/ChargeCommand", cmd.model_dump())
        return ApiResponse(data=result)

    async def enable(self, robot_id: str, cmd: EnableCommand) -> ApiResponse:
        result = await self._ros2.call_service("/EnableCommand", cmd.model_dump())
        return ApiResponse(data=result)
