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
    """Subscribes to /robot_status (interface_pkg/msg/Robotstatus) and pushes to StatusService.

    The hardware-side arm controller publishes Robotstatus; this listener flattens
    it into a dict that StatusService can broadcast over WebSocket.
    """

    STATUS_TOPIC = "/robot_status"
    DEFAULT_ROBOT_ID = "robot_001"
    BROADCAST_INTERVAL_S = 0.5  # throttle hardware ~10Hz down to 2Hz for the UI

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
        logger.info("Subscribed to %s (interface_pkg/msg/Robotstatus)", self.STATUS_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.STATUS_TOPIC)

    @staticmethod
    def _build_arm_state(joint_positions, tcp_pose) -> dict:
        joints = list(joint_positions)
        # StatusPayload's ArmState requires exactly 7 joints; pad/truncate defensively.
        if len(joints) < 7:
            joints = joints + [0.0] * (7 - len(joints))
        elif len(joints) > 7:
            joints = joints[:7]

        pose = list(tcp_pose) + [0.0] * max(0, 6 - len(tcp_pose))
        return {
            "joint_angles": [float(j) for j in joints],
            "end_effector": {
                "x": float(pose[0]),
                "y": float(pose[1]),
                "z": float(pose[2]),
                "roll": float(pose[3]),
                "pitch": float(pose[4]),
                "yaw": float(pose[5]),
            },
            "coordinate_frame": "base_link",
            "status": "idle",
        }

    def _on_status_message(self, msg):
        if self._status_service is None:
            return
        now = time.monotonic()
        if now - self._last_broadcast_ts < self.BROADCAST_INTERVAL_S:
            return
        self._last_broadcast_ts = now
        try:
            # Robotstatus carries alarm/enable info. Joint angles and end-effector
            # pose are owned by the joint_state_listener (which uses /joint_states
            # + TF), so we merge rather than overwrite the arm field.
            existing = self._status_service.get_latest(self.DEFAULT_ROBOT_ID) or {}
            arm = existing.get("arm") or {
                "left": self._build_arm_state(msg.left_joint_positions, msg.left_tcp_pose),
                "right": self._build_arm_state(msg.right_joint_positions, msg.right_tcp_pose),
            }
            data = {
                "position": existing.get("position", {"x": 0.0, "y": 0.0, "theta": 0.0}),
                "gripper": existing.get("gripper") or {
                    "left": {"state": "open", "force": 0.0},
                    "right": {"state": "open", "force": 0.0},
                },
                "enabled": bool(msg.is_enabled),
                "error_code": 1 if bool(msg.is_alarming) else 0,
                "task_status": "idle",
                "arm": arm,
            }
            self._runtime.call_async_in_loop(
                self._status_service.push_status(self.DEFAULT_ROBOT_ID, data)
            )
        except Exception:
            logger.exception("Error processing Robotstatus message")
