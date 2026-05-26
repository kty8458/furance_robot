import os
import tempfile

import pytest
from unittest.mock import AsyncMock

from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.services.status_service import StatusService
from app.services.log_service import LogService
from app.ros2.factory import Ros2Components
from app.ros2.service_client import MockRos2ServiceClient
from app.ros2.log_collector import MockRos2LogCollector
from app.ros2.topic_listener import MockRos2TopicListener
from app.ros2.joint_state_listener import MockJointStateListener
from app.ros2.moveit_client import MockMoveItServiceClient
from app.ros2.arm_enable_client import MockArmEnableClient


@pytest.fixture
def mock_ros2_client():
    client = AsyncMock()
    client.call_service = AsyncMock(return_value={"success": True, "message": "ok"})
    return client


@pytest.fixture
def app(tmp_path):
    """Create app with mock ROS2 components, properly triggering lifespan."""
    # Override teach_data_dir to a temp dir for testing
    os.environ["TEACH_DATA_DIR"] = str(tmp_path / "teach")
    application = create_app()
    # Manually set app.state as lifespan would do
    # (httpx ASGITransport doesn't trigger lifespan events)
    application.state.ros2 = Ros2Components(
        runtime=None,
        service_client=MockRos2ServiceClient(),
        log_collector=MockRos2LogCollector(),
        topic_listener=MockRos2TopicListener(),
        joint_state_listener=MockJointStateListener(),
        moveit_client=MockMoveItServiceClient(),
        arm_enable_client=MockArmEnableClient(),
    )
    application.state.status_service = StatusService()
    application.state.log_service = LogService()
    yield application
    # Cleanup env
    os.environ.pop("TEACH_DATA_DIR", None)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
