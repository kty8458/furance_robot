import logging
import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from sensor_msgs.msg import JointState

    HAS_RCLPY = True
except ImportError:
    HAS_RCLPY = False

LEFT_JOINT_NAMES = [f"ARM-L-J{i}_Joint" for i in range(1, 8)]
RIGHT_JOINT_NAMES = [f"ARM-R-J{i}_Joint" for i in range(1, 8)]


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
    """Subscribes to /joint_states and pushes arm data to StatusService.

    Extracts left/right arm joint angles from JointState messages and
    merges them into the existing status data.
    """

    JOINT_STATES_TOPIC = "/joint_states"

    def __init__(self, runtime):
        if not HAS_RCLPY:
            raise RuntimeError("rclpy is not installed")
        self._runtime = runtime
        self._sub = None
        self._status_service: "StatusService | None" = None

    async def start(self, status_service: "StatusService"):
        self._status_service = status_service
        node = self._runtime.node
        self._sub = node.create_subscription(
            JointState,
            self.JOINT_STATES_TOPIC,
            self._on_joint_state,
            10,
        )
        logger.info("Subscribed to %s", self.JOINT_STATES_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.JOINT_STATES_TOPIC)

    def _on_joint_state(self, msg: JointState):
        if self._status_service is None:
            return

        left_angles = [0.0] * 7
        right_angles = [0.0] * 7

        name_to_index = {name: i for i, name in enumerate(msg.name)}

        for i, name in enumerate(LEFT_JOINT_NAMES):
            if name in name_to_index:
                idx = name_to_index[name]
                left_angles[i] = math.degrees(msg.position[idx])

        for i, name in enumerate(RIGHT_JOINT_NAMES):
            if name in name_to_index:
                idx = name_to_index[name]
                right_angles[i] = math.degrees(msg.position[idx])

        arm_data = {
            "arm": {
                "left": {
                    "joint_angles": left_angles,
                    "end_effector": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "coordinate_frame": "base_link",
                    "status": "idle",
                },
                "right": {
                    "joint_angles": right_angles,
                    "end_effector": {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "coordinate_frame": "base_link",
                    "status": "idle",
                },
            }
        }

        robot_id = "robot_001"
        existing = self._status_service.get_latest(robot_id) or {}
        merged = {**existing, **arm_data}

        self._runtime.call_async_in_loop(
            self._status_service.push_status(robot_id, merged)
        )