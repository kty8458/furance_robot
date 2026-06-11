"""Subscribe /motor_feedback (interface_pkg/msg/MotFeedback) and cache key fields.

Only three fields are exposed:
  - head_pan_deg     : msg.angle           (头部偏转, deg)
  - lift_height_cm   : msg.pos / 100       (升降机高度, cm)
  - head_tilt_deg    : msg.head_back_angle (头部俯仰, deg)

Other fields (errs, temps, currents, ready flags) are ignored per spec.
The cache is written into ``StatusService.update_ros2_cache`` under the
``motor`` key, and ChassisStatusPoller merges it into its periodic broadcast.
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from interface_pkg.msg import MotFeedback

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False


class MotorFeedbackListenerBase(ABC):
    @abstractmethod
    async def start(self, status_service: "StatusService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockMotorFeedbackListener(MotorFeedbackListenerBase):
    async def start(self, status_service: "StatusService"):
        pass

    async def stop(self):
        pass


class RealMotorFeedbackListener(MotorFeedbackListenerBase):
    """Subscribes to /motor_feedback and writes head pan/tilt + lift height
    to StatusService's ROS2 cache."""

    TOPIC = "/motor_feedback"
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
            MotFeedback, self.TOPIC, self._on_message, 10,
        )
        logger.info("Subscribed to %s (interface_pkg/msg/MotFeedback)", self.TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.TOPIC)

    def _on_message(self, msg):
        if self._status_service is None:
            return
        now = time.monotonic()
        throttled = (now - self._last_broadcast_ts) >= self.BROADCAST_INTERVAL_S
        try:
            data = {
                "motor": {
                    "head_pan_deg": float(msg.angle),
                    "lift_height_cm": float(msg.pos) / 100.0,
                    "head_tilt_deg": float(msg.head_back_angle),
                },
            }
            self._runtime.call_async_in_loop(
                self._status_service.update_ros2_cache(self.DEFAULT_ROBOT_ID, data)
            )
            # Push independently so motor data reaches frontend even when
            # chassis is unreachable.  Mark ros2_motor source as fresh.
            self._status_service.mark_source_fresh(self.DEFAULT_ROBOT_ID, "ros2_motor")
            if throttled:
                self._last_broadcast_ts = now
                self._runtime.call_async_in_loop(
                    self._status_service.push_ros2_snapshot(self.DEFAULT_ROBOT_ID)
                )
        except Exception:
            logger.exception("Failed to process MotFeedback")
