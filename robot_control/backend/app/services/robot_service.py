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
        # 调用 modbus_gripper 的 /gripper_control service (GripperControl srv 类型)
        try:
            from control_interfaces.srv import GripperControl
            from rclpy.node import Node
        except ImportError:
            # Fallback: 旧的 GripperCommand service (Mock 或 非 modbus 节点)
            result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
            return _check_result(result)

        # 通过 ros2 runtime 直接调用 GripperControl
        runtime = getattr(self._ros2, "_runtime", None)
        if runtime is None:
            result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
            return _check_result(result)

        node: Node = runtime.node
        client = node.create_client(GripperControl, "/gripper_control")
        if not client.wait_for_service(timeout_sec=2.0):
            return _check_result({"success": False, "message": "/gripper_control service not available"})

        req = GripperControl.Request()
        req.arm = cmd.arm.value if hasattr(cmd.arm, "value") else str(cmd.arm)
        req.method = cmd.action.value if hasattr(cmd.action, "value") else str(cmd.action)
        req.torque = float(cmd.force)
        req.position = float(cmd.position)

        import asyncio
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()
        ros_future = client.call_async(req)

        def _done(fut):
            if aio_future.done(): return
            try:
                resp = fut.result()
                loop.call_soon_threadsafe(aio_future.set_result, {
                    "success": bool(resp.success),
                    "message": resp.gripper_message,
                    "data": {
                        "status": resp.gripper_status,
                        "current_position": float(resp.current_position),
                    },
                })
            except Exception as e:
                loop.call_soon_threadsafe(aio_future.set_exception, e)
        ros_future.add_done_callback(_done)
        try:
            result = await asyncio.wait_for(aio_future, timeout=10.0)
        except asyncio.TimeoutError:
            result = {"success": False, "message": "Gripper service timed out"}
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
