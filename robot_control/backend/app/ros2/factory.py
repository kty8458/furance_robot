import ctypes
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

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
from app.ros2.joint_state_listener import (
    MockJointStateListener,
    RealJointStateListener,
    JointStateListenerBase,
)
from app.ros2.moveit_client import (
    MockMoveItServiceClient,
    RealMoveItServiceClient,
    MoveItServiceClientBase,
)
from app.ros2.arm_enable_client import (
    ArmEnableClientBase,
    MockArmEnableClient,
    RealArmEnableClient,
)
from app.ros2.upper_body_client import (
    MockUpperBodyClient,
    RealUpperBodyClient,
    UpperBodyClientBase,
)
from app.ros2.camera_client import (
    CameraClientBase,
    MockCameraClient,
    RealCameraClient,
)
from app.ros2.motor_feedback_listener import (
    MockMotorFeedbackListener,
    RealMotorFeedbackListener,
    MotorFeedbackListenerBase,
)

logger = logging.getLogger(__name__)

# Directory where CMake post-build copies furance_interfaces install output
_BACKEND_ROS2_LIBS = Path(__file__).resolve().parent.parent.parent / "ros2_libs"


def _setup_ros2_workspace():
    """Set up sys.path and preload .so libraries from local ros2_libs directory."""
    if not _BACKEND_ROS2_LIBS.is_dir():
        logger.warning("ros2_libs directory not found: %s", _BACKEND_ROS2_LIBS)
        return

    # Add Python dist-packages to sys.path
    for py_dir in _BACKEND_ROS2_LIBS.rglob("dist-packages"):
        resolved = str(py_dir.resolve())
        if resolved not in sys.path:
            sys.path.insert(0, resolved)
            logger.info("Added to sys.path: %s", resolved)

    # Preload native .so libraries via ctypes so the dynamic linker can find them
    lib_dir = _BACKEND_ROS2_LIBS / "lib"
    if lib_dir.is_dir():
        for so_file in sorted(lib_dir.glob("*.so")):
            try:
                ctypes.CDLL(str(so_file))
                logger.debug("Preloaded: %s", so_file.name)
            except OSError as e:
                logger.warning("Failed to preload %s: %s", so_file.name, e)


@dataclass
class Ros2Components:
    """Holds all ROS2 components for the application."""

    service_client: Ros2ServiceClientBase
    log_collector: Ros2LogCollectorBase
    topic_listener: Ros2TopicListenerBase
    joint_state_listener: JointStateListenerBase
    moveit_client: MoveItServiceClientBase
    arm_enable_client: ArmEnableClientBase
    upper_body_client: UpperBodyClientBase
    camera_client: CameraClientBase
    motor_feedback_listener: MotorFeedbackListenerBase
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
            _setup_ros2_workspace()
            from app.ros2.runtime import Ros2Runtime

            runtime = Ros2Runtime(domain_id=settings.ros2_domain_id)
            components = Ros2Components(
                runtime=runtime,
                service_client=RealRos2ServiceClient(
                    runtime, timeout=settings.ros2_service_timeout
                ),
                log_collector=RealRos2LogCollector(runtime),
                topic_listener=RealRos2TopicListener(runtime),
                joint_state_listener=RealJointStateListener(runtime),
                moveit_client=RealMoveItServiceClient(runtime, timeout=settings.ros2_service_timeout),
                arm_enable_client=RealArmEnableClient(runtime, timeout=settings.ros2_service_timeout),
                upper_body_client=RealUpperBodyClient(runtime, timeout=settings.ros2_service_timeout),
                camera_client=RealCameraClient(runtime=runtime, timeout=settings.ros2_service_timeout),
                motor_feedback_listener=RealMotorFeedbackListener(runtime),
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
        joint_state_listener=MockJointStateListener(),
        moveit_client=MockMoveItServiceClient(),
        arm_enable_client=MockArmEnableClient(),
        upper_body_client=MockUpperBodyClient(),
        camera_client=MockCameraClient(),
        motor_feedback_listener=MockMotorFeedbackListener(),
    )
    logger.info("ROS2 components created in MOCK mode")
    return components
