import logging
import math
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from interface_pkg.msg import Robotstatus
    import tf2_ros
    from rclpy.time import Time

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

# End-effector TF frames (joint 7 link) per arm side, expressed in base_link.
LEFT_EE_FRAME = "ARM-L-J7_Link"
RIGHT_EE_FRAME = "ARM-R-J7_Link"
BASE_FRAME = "base_link"


def _quat_to_rpy_deg(qx: float, qy: float, qz: float, qw: float) -> tuple[float, float, float]:
    """Convert quaternion to roll/pitch/yaw (XYZ intrinsic) in degrees."""
    sinr_cosp = 2.0 * (qw * qx + qy * qz)
    cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
    roll = math.atan2(sinr_cosp, cosr_cosp)
    sinp = 2.0 * (qw * qy - qz * qx)
    if abs(sinp) >= 1:
        pitch = math.copysign(math.pi / 2, sinp)
    else:
        pitch = math.asin(sinp)
    siny_cosp = 2.0 * (qw * qz + qx * qy)
    cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
    yaw = math.atan2(siny_cosp, cosy_cosp)
    return math.degrees(roll), math.degrees(pitch), math.degrees(yaw)


def _pad_to_seven(values) -> list[float]:
    arr = [float(v) for v in values]
    if len(arr) < 7:
        arr += [0.0] * (7 - len(arr))
    elif len(arr) > 7:
        arr = arr[:7]
    return arr


class JointStateListenerBase(ABC):
    @abstractmethod
    async def start(self, status_service: "StatusService"):
        ...

    @abstractmethod
    async def stop(self):
        ...


class MockJointStateListener(JointStateListenerBase):
    async def start(self, status_service: "StatusService"):
        pass

    async def stop(self):
        pass


class RealJointStateListener(JointStateListenerBase):
    """Subscribes to /robot_status and publishes arm joint angles + EE pose.

    Joint angles come directly from Robotstatus (already in degrees from
    hardware). End-effector pose is the TF transform of ARM-{L,R}-J7_Link in
    base_link — translation m -> mm, orientation -> RPY degrees.

    A separate node will publish /joint_states for MoveIt; this listener
    intentionally does not subscribe there to avoid topic ownership conflicts.
    """

    STATUS_TOPIC = "/robot_status"
    BROADCAST_INTERVAL_S = 0.5
    DEFAULT_ROBOT_ID = "robot_001"

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy / tf2_ros is not installed")
        self._runtime = runtime
        self._sub = None
        self._status_service: "StatusService | None" = None
        self._tf_buffer = None
        self._tf_listener = None
        self._last_broadcast_ts: float = 0.0

    async def start(self, status_service: "StatusService"):
        self._status_service = status_service
        node = self._runtime.node
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, node)
        self._sub = node.create_subscription(
            Robotstatus,
            self.STATUS_TOPIC,
            self._on_status_message,
            10,
        )
        logger.info("JointStateListener subscribed to %s and started TF listener", self.STATUS_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("JointStateListener unsubscribed from %s", self.STATUS_TOPIC)
        self._tf_listener = None
        self._tf_buffer = None

    def _lookup_ee_pose(self, ee_frame: str) -> dict:
        zero = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        if self._tf_buffer is None:
            return zero
        try:
            tr = self._tf_buffer.lookup_transform(BASE_FRAME, ee_frame, Time())
        except Exception:
            return zero
        t = tr.transform.translation
        q = tr.transform.rotation
        roll, pitch, yaw = _quat_to_rpy_deg(q.x, q.y, q.z, q.w)
        return {
            "x": float(t.x) * 1000.0,
            "y": float(t.y) * 1000.0,
            "z": float(t.z) * 1000.0,
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
        }

    def _on_status_message(self, msg):
        if self._status_service is None:
            return
        now = time.monotonic()
        throttled = (now - self._last_broadcast_ts) >= self.BROADCAST_INTERVAL_S

        arm_data = {
            "arm": {
                "left": {
                    "joint_angles": _pad_to_seven(msg.left_joint_positions),
                    "end_effector": self._lookup_ee_pose(LEFT_EE_FRAME),
                    "coordinate_frame": BASE_FRAME,
                    "status": "idle",
                },
                "right": {
                    "joint_angles": _pad_to_seven(msg.right_joint_positions),
                    "end_effector": self._lookup_ee_pose(RIGHT_EE_FRAME),
                    "coordinate_frame": BASE_FRAME,
                    "status": "idle",
                },
            }
        }

        self._runtime.call_async_in_loop(
            self._status_service.update_ros2_cache(self.DEFAULT_ROBOT_ID, arm_data)
        )
        # Push independently so joint/EE data reaches frontend even when
        # chassis is unreachable.  Mark ros2_joint source as fresh.
        self._status_service.mark_source_fresh(self.DEFAULT_ROBOT_ID, "ros2_joint")
        if throttled:
            self._last_broadcast_ts = now
            self._runtime.call_async_in_loop(
                self._status_service.push_ros2_snapshot(self.DEFAULT_ROBOT_ID)
            )
