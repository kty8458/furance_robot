import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router
from app.api.upper_body import router as upper_body_router
from app.api.workflow import router as workflow_router
from app.api.camera import router as camera_router
from app.ws.status import router as status_ws_router
from app.ws.logs import router as logs_ws_router
from app.ros2.factory import create_ros2_components
from app.services.status_service import StatusService
from app.services.log_service import LogService
from app.services.chassis_client import ChassisClient, MockChassisClient
from app.services.chassis_poller import ChassisStatusPoller
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    status_service = StatusService()
    log_service = LogService()
    components = create_ros2_components()

    # Start real ROS2 runtime if available
    if components.runtime is not None:
        components.runtime.start(asyncio.get_event_loop())
        await components.log_collector.start(log_service)
        await components.topic_listener.start(status_service)
        await components.joint_state_listener.start(status_service)

    # Store on app.state for access from API endpoints and WS handlers
    app.state.ros2 = components
    app.state.status_service = status_service
    app.state.log_service = log_service

    # Chassis client (HTTP direct, no ROS2)
    settings = get_settings()
    try:
        chassis_client = ChassisClient(
            base_url=settings.chassis_base_url,
            user_code=settings.chassis_user_code,
            password=settings.chassis_password,
            timeout=settings.chassis_timeout,
        )
    except Exception:
        logger.warning("Failed to create ChassisClient, using mock")
        chassis_client = MockChassisClient()
    app.state.chassis_client = chassis_client

    # Chassis status poller (poll hardware status every 1s)
    chassis_poller = ChassisStatusPoller(chassis_client, status_service)
    await chassis_poller.start()
    app.state.chassis_poller = chassis_poller

    logger.info(
        "Application started (ROS2_MODE=%s)",
        os.environ.get("ROS2_MODE", "mock"),
    )
    yield

    # Shutdown
    await chassis_client.close()
    await chassis_poller.stop()
    if components.runtime is not None:
        await components.log_collector.stop()
        await components.joint_state_listener.stop()
        await components.topic_listener.stop()
        components.runtime.stop()
    logger.info("Application stopped")


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0", lifespan=lifespan)
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    app.include_router(upper_body_router)
    app.include_router(workflow_router)
    app.include_router(camera_router)
    app.include_router(status_ws_router)
    app.include_router(logs_ws_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
