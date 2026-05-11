import os
import pytest
from app.ros2.factory import create_ros2_components
from app.ros2.service_client import MockRos2ServiceClient
from app.ros2.log_collector import MockRos2LogCollector
from app.ros2.topic_listener import MockRos2TopicListener


class TestFactoryMockMode:
    def test_default_creates_mock_components(self):
        os.environ.pop("ROS2_MODE", None)
        components = create_ros2_components()
        assert isinstance(components.service_client, MockRos2ServiceClient)
        assert isinstance(components.log_collector, MockRos2LogCollector)
        assert isinstance(components.topic_listener, MockRos2TopicListener)
        assert components.runtime is None

    def test_explicit_mock_mode(self):
        os.environ["ROS2_MODE"] = "mock"
        try:
            components = create_ros2_components()
            assert isinstance(components.service_client, MockRos2ServiceClient)
            assert components.runtime is None
        finally:
            os.environ.pop("ROS2_MODE", None)


class TestFactoryRealModeFallback:
    def test_real_mode_falls_back_to_mock_without_rclpy(self):
        """Real mode should fall back to mock if rclpy is not available."""
        os.environ["ROS2_MODE"] = "real"
        try:
            components = create_ros2_components()
            # Without a full ROS2 environment, factory falls back to mock
            assert isinstance(components.service_client, MockRos2ServiceClient)
            assert components.runtime is None
        finally:
            os.environ.pop("ROS2_MODE", None)
