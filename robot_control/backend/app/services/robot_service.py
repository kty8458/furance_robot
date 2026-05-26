from furance_shared.protocol.http_schema import ApiResponse
from furance_shared.models.command import (
    HomeCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from app.ros2.service_client import Ros2ServiceClientBase
from app.ros2.arm_enable_client import ArmEnableClientBase


ROS2_SERVICE_MAP = {
    "home": "/HomeCommand",
    "grab": "/GrabCommand",
    "place": "/PlaceCommand",
    "gripper": "/GripperCommand",
    "lift": "/LiftCommand",
    "charge": "/ChargeCommand",
}


def _check_result(result: dict) -> ApiResponse:
    if result.get("success") is False:
        return ApiResponse(code=1001, message=result.get("message", "ROS2 服务调用失败"))
    return ApiResponse(data=result)


class RobotService:
    def __init__(
        self,
        ros2_client: Ros2ServiceClientBase,
        arm_enable_client: ArmEnableClientBase | None = None,
    ):
        self._ros2 = ros2_client
        self._arm_enable = arm_enable_client

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
        if self._arm_enable is None:
            return ApiResponse(code=1001, message="ArmEnableClient 未初始化")
        # Enabling while the controller is in an alarm state is rejected by the
        # hardware ("disabled or enable failed!"), so always clear errors first
        # when transitioning to enabled. clear_error flag forces a clear even on
        # disable.
        if cmd.enable or cmd.clear_error:
            result = await self._arm_enable.clear_error()
            if result.get("success") is False:
                return _check_result(result)
        result = await self._arm_enable.enable(cmd.enable)
        return _check_result(result)

    async def clear_error(self, robot_id: str) -> ApiResponse:
        if self._arm_enable is None:
            return ApiResponse(code=1001, message="ArmEnableClient 未初始化")
        result = await self._arm_enable.clear_error()
        return _check_result(result)
