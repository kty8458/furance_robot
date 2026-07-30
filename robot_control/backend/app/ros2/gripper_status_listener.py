"""EtherCAT 夹爪状态监听器。

订阅 /gripper_node/EC_grippers_status (control_interfaces/msg/ECGrippersStatus),
将左右夹爪的实时状态 (claw_status, width, voltage, temperature, errors) 更新到 StatusService。
"""

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from control_interfaces.msg import ECGrippersStatus

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class GripperStatusListenerBase(ABC):
    @abstractmethod
    async def start(self, status_service: "StatusService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockGripperStatusListener(GripperStatusListenerBase):
    async def start(self, status_service: "StatusService"):
        pass

    async def stop(self):
        pass


class RealGripperStatusListener(GripperStatusListenerBase):
    """订阅 EtherCAT 夹爪状态 topic, 更新 StatusService。"""

    STATUS_TOPIC = "/gripper_node/EC_grippers_status"

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("control_interfaces / rclpy not available")
        self._runtime = runtime
        self._sub = None
        self._status_service: "StatusService | None" = None

    async def start(self, status_service: "StatusService"):
        self._status_service = status_service
        node = self._runtime.node
        self._sub = node.create_subscription(
            ECGrippersStatus,
            self.STATUS_TOPIC,
            self._on_status,
            10,
        )
        logger.info("GripperStatusListener subscribed to %s", self.STATUS_TOPIC)

    async def stop(self):
        if self._sub is not None and self._runtime is not None:
            try:
                self._runtime.node.destroy_subscription(self._sub)
            except Exception:
                pass
            self._sub = None

    def _on_status(self, msg: "ECGrippersStatus"):
        """收到夹爪状态, 更新 status_service 并推送 WS。"""
        if self._status_service is None:
            return

        # claw_status 状态码: 3=ready, 5=open reached, 6=closing, 7=grip ok, 8=empty grip, 10=fault
        claw_status_map = {
            0: "not_init", 1: "wait_homing", 2: "homing", 3: "ready",
            4: "opening", 5: "open", 6: "closing", 7: "grip_ok",
            8: "empty_grip", 9: "dropped", 10: "fault",
        }
        state_text = claw_status_map.get(msg.claw_status, f"unknown({msg.claw_status})")
        has_error = msg.claw_error != 0 or msg.motor_error != 0

        gripper_data = {
            "state": state_text,
            "claw_status": int(msg.claw_status),
            "claw_status_text": msg.claw_status_text,
            "claw_error": int(msg.claw_error),
            "motor_error": int(msg.motor_error),
            "current_width_mm": float(msg.current_width_mm),
            "bus_voltage_v": float(msg.bus_voltage_v),
            "driver_temperature_c": float(msg.driver_temperature_c),
            "online": bool(msg.online),
            "has_error": has_error,
        }

        # 按 gripper_name (left/right) 更新
        name = msg.gripper_name or "right"
        self._status_service.update_gripper_status(name, gripper_data)

        # 触发 WS 推送 (让前端实时看到夹爪状态)
        self._runtime.call_async_in_loop(
            self._status_service.push_ros2_snapshot("robot_001")
        )
