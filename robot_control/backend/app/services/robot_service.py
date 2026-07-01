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
        import logging as _log
        _l = _log.getLogger("app.services.robot_service")
        # 调用 modbus_gripper 的 /gripper_control service (GripperControl srv 类型)
        try:
            from control_interfaces.srv import GripperControl
            from rclpy.node import Node
        except ImportError as ie:
            _l.warning("GripperControl 导入失败, fallback 到 /GripperCommand: %s", ie)
            result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
            return _check_result(result)

        runtime = getattr(self._ros2, "_runtime", None)
        if runtime is None:
            _l.warning("ROS2 runtime 不可用, fallback 到 /GripperCommand")
            result = await self._ros2.call_service("/GripperCommand", cmd.model_dump())
            return _check_result(result)

        node: Node = runtime.node
        client = node.create_client(GripperControl, "/gripper_control")
        if not client.wait_for_service(timeout_sec=2.0):
            _l.warning("/gripper_control service not available")
            return _check_result({"success": False, "message": "/gripper_control service not available"})

        req = GripperControl.Request()
        req.arm = cmd.arm.value if hasattr(cmd.arm, "value") else str(cmd.arm)
        req.method = cmd.action.value if hasattr(cmd.action, "value") else str(cmd.action)
        req.torque = float(cmd.force)
        req.position = float(cmd.position)
        _l.info("调用 /gripper_control: arm=%s method=%s torque=%.1f position=%.1f",
                req.arm, req.method, req.torque, req.position)

        import asyncio
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()
        ros_future = client.call_async(req)

        def _done(fut):
            if aio_future.done(): return
            try:
                resp = fut.result()
                _l.info("/gripper_control 响应: success=%s message=%s", resp.success, resp.gripper_message)
                loop.call_soon_threadsafe(aio_future.set_result, {
                    "success": bool(resp.success),
                    "message": resp.gripper_message,
                    "data": {
                        "status": resp.gripper_status,
                        "current_position": float(resp.current_position),
                    },
                })
            except Exception as e:
                _l.error("/gripper_control 回调异常: %s", e)
                loop.call_soon_threadsafe(aio_future.set_exception, e)
        ros_future.add_done_callback(_done)
        try:
            result = await asyncio.wait_for(aio_future, timeout=10.0)
            _l.info("/gripper_control 结果: %s", result)
        except asyncio.TimeoutError:
            _l.warning("/gripper_control 超时")
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
