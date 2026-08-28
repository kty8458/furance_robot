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
        # 调用 EtherCAT 夹爪节点 /gripper_node/EC_grippers_control (ECGrippersControl srv)
        try:
            from control_interfaces.srv import ECGrippersControl
            from rclpy.node import Node
        except ImportError as ie:
            _l.warning("ECGrippersControl 导入失败: %s", ie)
            return _check_result({"success": False, "message": f"ECGrippersControl 接口不可用: {ie}"})

        runtime = getattr(self._ros2, "_runtime", None)
        if runtime is None:
            _l.warning("ROS2 runtime 不可用")
            return _check_result({"success": False, "message": "ROS2 runtime 不可用"})

        node: Node = runtime.node
        client = node.create_client(ECGrippersControl, "/gripper_node/EC_grippers_control")
        if not client.wait_for_service(timeout_sec=2.0):
            _l.warning("/gripper_node/EC_grippers_control service not available")
            return _check_result({"success": False, "message": "EtherCAT 夹爪服务未启动"})

        # 映射: arm -> gripper_name, action -> command, position(0-100%) -> width_mm(100-180)
        gripper_name = cmd.arm.value if hasattr(cmd.arm, "value") else str(cmd.arm)
        action_str = cmd.action.value if hasattr(cmd.action, "value") else str(cmd.action)
        # open/close 直接映射, position -> move, clear_error -> 节点端清错指令
        command_map = {"open": "open", "close": "close", "position": "move",
                       "clear_error": "clear_error"}
        command = command_map.get(action_str, action_str)
        # position 0-100% -> width_mm 100-180mm (0%=闭合100mm, 100%=张开180mm)
        width_mm = 100.0 + (cmd.position / 100.0) * 80.0 if command == "move" else 0.0

        req = ECGrippersControl.Request()
        req.gripper_name = gripper_name
        req.command = command
        req.width_mm = float(width_mm)
        _l.info("调用 /gripper_node/EC_grippers_control: gripper=%s command=%s width=%.1fmm",
                req.gripper_name, req.command, req.width_mm)

        import asyncio
        loop = asyncio.get_event_loop()
        aio_future = loop.create_future()
        ros_future = client.call_async(req)

        def _done(fut):
            if aio_future.done(): return
            try:
                resp = fut.result()
                _l.info("EC_grippers 响应: success=%s message=%s width=%.1fmm",
                        resp.success, resp.message, resp.current_width_mm)
                loop.call_soon_threadsafe(aio_future.set_result, {
                    "success": bool(resp.success),
                    "message": resp.message,
                    "data": {
                        "current_width_mm": float(resp.current_width_mm),
                        "claw_status": int(resp.claw_status),
                        "claw_error": int(resp.claw_error),
                        "motor_error": int(resp.motor_error),
                    },
                })
            except Exception as e:
                _l.error("EC_grippers 回调异常: %s", e)
                loop.call_soon_threadsafe(aio_future.set_exception, e)
        ros_future.add_done_callback(_done)
        try:
            result = await asyncio.wait_for(aio_future, timeout=15.0)
            _l.info("EC_grippers 结果: %s", result)
        except asyncio.TimeoutError:
            _l.warning("EC_grippers 超时")
            result = {"success": False, "message": "EtherCAT 夹爪服务超时"}
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
