import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.log_service import LogService

try:
    from rcl_interfaces.msg import Log as RosLog

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

# ROS2 log level constants from rcl_interfaces/msg/Log
_ROS2_LEVEL_MAP = {
    RosLog.DEBUG: "debug",
    RosLog.INFO: "info",
    RosLog.WARN: "warn",
    RosLog.ERROR: "error",
    RosLog.FATAL: "error",
} if HAS_RCLPY else {}


class Ros2LogCollectorBase(ABC):
    @abstractmethod
    async def start(self, log_service: "LogService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockRos2LogCollector(Ros2LogCollectorBase):
    async def start(self, log_service: "LogService"):
        pass

    async def stop(self):
        pass


class RealRos2LogCollector(Ros2LogCollectorBase):
    """Subscribes to /rosout topic and pushes logs to LogService.

    Topic: /rosout
    Type: rcl_interfaces/msg/Log
    """

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._sub = None
        self._log_service: "LogService | None" = None

    async def start(self, log_service: "LogService"):
        self._log_service = log_service
        node = self._runtime.node
        self._sub = node.create_subscription(
            RosLog,
            "/rosout",
            self._on_log_message,
            100,
        )
        logger.info("Subscribed to /rosout")

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from /rosout")

    def _on_log_message(self, msg: RosLog):
        """Callback for /rosout messages. Bridges to asyncio."""
        if self._log_service is None:
            return
        level = _ROS2_LEVEL_MAP.get(msg.level, "info")
        self._runtime.call_async_in_loop(
            self._log_service.push_log(
                source="ros2",
                level=level,
                message=msg.msg,
                node=msg.name,
            )
        )
