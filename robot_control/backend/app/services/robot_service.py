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


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


class RobotService:
    def __init__(self, ros2_client: Ros2ServiceClientBase):
        self._ros2 = ros2_client

    async def home(self, robot_id: str) -> ApiResponse:
        result = await self._ros2.call_service("/HomeCommand", {})
        return _check_result(result)

    async def grab(self, robot_id: str, cmd: GrabCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GrabCommand", cmd.model_dump())
        return _check_result(result)

    async def place(self, robot_id: str, cmd: PlaceCommand) -> ApiResponse:
        result = await self._ros2.call_service("/PlaceCommand", cmd.model_dump())
        return _check_result(result)

    async def gripper(self, robot_id: str, cmd: GripperCommand) -> ApiResponse:
        result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
        return _check_result(result)

    async def lift(self, robot_id: str, cmd: LiftCommand) -> ApiResponse:
        result = await self._ros2.call_service("/LiftCommand", cmd.model_dump())
        return _check_result(result)

    async def charge(self, robot_id: str, cmd: ChargeCommand) -> ApiResponse:
        result = await self._ros2.call_service("/ChargeCommand", cmd.model_dump())
        return _check_result(result)

    async def enable(self, robot_id: str, cmd: EnableCommand) -> ApiResponse:
        result = await self._ros2.call_service("/EnableCommand", cmd.model_dump())
        return _check_result(result)
