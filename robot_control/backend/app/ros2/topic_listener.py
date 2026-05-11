import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.status_service import StatusService

try:
    from std_msgs.msg import String as StringMsg

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
    """Subscribes to /robot_status topic and pushes data to StatusService.

    Topic: /robot_status
    Type: std_msgs/String
    Payload: JSON-encoded StatusPayload dict
    """

    STATUS_TOPIC = "/robot_status"

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
            StringMsg,
            self.STATUS_TOPIC,
            self._on_status_message,
            10,
        )
        logger.info("Subscribed to %s", self.STATUS_TOPIC)

    async def stop(self):
        if self._sub and self._runtime.is_running:
            self._runtime.node.destroy_subscription(self._sub)
            self._sub = None
            logger.info("Unsubscribed from %s", self.STATUS_TOPIC)

    def _on_status_message(self, msg: StringMsg):
        """Callback for /robot_status messages. Bridges to asyncio."""
        if self._status_service is None:
            return
        try:
            data = json.loads(msg.data)
            robot_id = data.get("robot_id", "robot_001")
            self._runtime.call_async_in_loop(
                self._status_service.push_status(robot_id, data)
            )
        except json.JSONDecodeError:
            logger.warning("Invalid JSON on %s: %s", self.STATUS_TOPIC, msg.data[:200])
        except Exception:
            logger.exception("Error processing status message")
