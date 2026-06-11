import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from interface_pkg.msg import Robotstatus

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class Ros2TopicListenerBase(ABC):
    @abstractmethod
    async def start(self, status_service: "StatusService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockRos2TopicListener(Ros2TopicListenerBase):
    async def start(self, status_service: "StatusService"):
        pass

    async def stop(self):
        pass


class RealRos2TopicListener(Ros2TopicListenerBase):
    """Subscribes to /robot_status for enabled/error_code only.

    Arm joint angles and end-effector pose come from
    RealJointStateListener, which uses TF lookups for TCP —
    that is the authoritative source.
    """

    STATUS_TOPIC = "/robot_status"
    DEFAULT_ROBOT_ID = "robot_001"
    BROADCAST_INTERVAL_S = 1.0  # throttle to 1Hz

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("interface_pkg / rclpy not available")
        self._runtime = runtime
        self._sub = None
        self._status_service: "StatusService | None" = None
        self._last_broadcast_ts: float = 0.0

    async def start(self, status_service: "StatusService"):
        self._status_service = status_service
        node = self._runtime.node
        self._sub = node.create_subscription(
            Robotstatus,
            self.STATUS_TOPIC,
            self._on_status_message,
            10,
        )
        logger.info("Subscribed to %s (enabled/error only)", self.STATUS_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.STATUS_TOPIC)

    def _on_status_message(self, msg):
        if self._status_service is None:
            return
        now = time.monotonic()
        throttled = (now - self._last_broadcast_ts) >= self.BROADCAST_INTERVAL_S
        try:
            data = {
                "enabled": bool(msg.is_enabled),
                "error_code": 1 if bool(msg.is_alarming) else 0,
            }
            self._runtime.call_async_in_loop(
                self._status_service.update_ros2_cache(self.DEFAULT_ROBOT_ID, data)
            )
            self._status_service.mark_source_fresh(self.DEFAULT_ROBOT_ID, "ros2_status")
            if throttled:
                self._last_broadcast_ts = now
                self._runtime.call_async_in_loop(
                    self._status_service.push_ros2_snapshot(self.DEFAULT_ROBOT_ID)
                )
        except Exception:
            logger.exception("Error processing Robotstatus message")
