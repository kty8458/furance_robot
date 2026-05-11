import logging
import os
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.ros2.log_collector import (
    MockRos2LogCollector,
    RealRos2LogCollector,
    Ros2LogCollectorBase,
)
from app.ros2.service_client import (
    MockRos2ServiceClient,
    RealRos2ServiceClient,
    Ros2ServiceClientBase,
)
from app.ros2.topic_listener import (
    MockRos2TopicListener,
    RealRos2TopicListener,
    Ros2TopicListenerBase,
)

logger = logging.getLogger(__name__)


@dataclass
class Ros2Components:
    """Holds all ROS2 components for the application."""

    service_client: Ros2ServiceClientBase
    log_collector: Ros2LogCollectorBase
    topic_listener: Ros2TopicListenerBase
    runtime: object | None  # Ros2Runtime when real mode, None when mock


def create_ros2_components(settings: Settings | None = None) -> Ros2Components:
    """Factory: create ROS2 components based on ROS2_MODE env var.

    ROS2_MODE=mock (default): Uses mock implementations, no rclpy needed.
    ROS2_MODE=real: Uses real rclpy implementations, requires ROS2 environment.
    """
    settings = settings or get_settings()
    mode = os.environ.get("ROS2_MODE", "mock").lower()

    if mode == "real":
        try:
            from app.ros2.runtime import Ros2Runtime

            runtime = Ros2Runtime(domain_id=settings.ros2_domain_id)
            components = Ros2Components(
                runtime=runtime,
                service_client=RealRos2ServiceClient(
                    runtime, timeout=settings.ros2_service_timeout
                ),
                log_collector=RealRos2LogCollector(runtime),
                topic_listener=RealRos2TopicListener(runtime),
            )
            logger.info("ROS2 components created in REAL mode (domain_id=%d)", settings.ros2_domain_id)
            return components
        except (ImportError, RuntimeError) as exc:
            logger.warning(
                "ROS2_MODE=real but rclpy unavailable (%s). Falling back to mock.", exc
            )

    # Mock mode (default or fallback)
    components = Ros2Components(
        runtime=None,
        service_client=MockRos2ServiceClient(),
        log_collector=MockRos2LogCollector(),
        topic_listener=MockRos2TopicListener(),
    )
    logger.info("ROS2 components created in MOCK mode")
    return components
