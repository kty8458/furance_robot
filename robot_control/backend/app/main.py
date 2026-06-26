import asyncio
import logging
import os
import traceback
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
from app.api.log_viewer import router as log_viewer_router
from app.ws.status import router as status_ws_router
from app.ws.logs import router as logs_ws_router
from app.ws.camera import router as camera_ws_router
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
    settings = get_settings()

    # File logging (daily rotation, before any logger call)
    from app.core.logging_setup import setup_file_logging
    setup_file_logging(
        log_dir=settings.log_dir,
        level=settings.log_level,
        retention_days=settings.log_retention_days,
    )

    status_service = StatusService()
    log_service = LogService()
    components = create_ros2_components()

    # Start real ROS2 runtime if available
    if components.runtime is not None:
        components.runtime.start(asyncio.get_event_loop())
        await components.log_collector.start(log_service)
        await components.topic_listener.start(status_service)
        await components.joint_state_listener.start(status_service)
        await components.motor_feedback_listener.start(status_service)

    # Store on app.state for access from API endpoints and WS handlers
    app.state.ros2 = components
    app.state.status_service = status_service
    app.state.log_service = log_service

    # Chassis client (HTTP direct, no ROS2)
    try:
        chassis_client = ChassisClient(
            base_url=settings.chassis_base_url,
            user_code=settings.chassis_user_code,
            password=settings.chassis_password,
            timeout=settings.chassis_timeout,
        )
    except Exception as e:
        logger.warning("Failed to create ChassisClient (%s: %s), using mock\n%s",
                       type(e).__name__, e, traceback.format_exc())
        chassis_client = MockChassisClient()
    app.state.chassis_client = chassis_client

    # Chassis status poller (poll hardware status every 1s)
    chassis_poller = ChassisStatusPoller(chassis_client, status_service)
    await chassis_poller.start()
    app.state.chassis_poller = chassis_poller

    # Periodic status heartbeat (60s) — logs one line summary so operators
    # can confirm the robot is alive via the log file.
    from app.services.status_heartbeat import StatusHeartbeat
    status_heartbeat = StatusHeartbeat(status_service)
    await status_heartbeat.start()
    app.state.status_heartbeat = status_heartbeat

    # Workflow service (singleton — keeps execution state across requests)
    from app.services.workflow_service import WorkflowService
    from app.services.arm_service import ArmService
    arm_service_for_wf = ArmService(
        ros2_client=components.service_client,
        moveit_client=components.moveit_client,
        teach_dir=settings.teach_data_dir,
    )
    app.state.workflow_service = WorkflowService(
        ros2_client=components.service_client,
        moveit_client=components.moveit_client,
        upper_body_client=components.upper_body_client,
        chassis_client=chassis_client,
        arm_service=arm_service_for_wf,
        arm_enable_client=components.arm_enable_client,
        workflow_dir=settings.workflow_data_dir,
        status_service=status_service,
        joint_state_listener=components.joint_state_listener,
    )

    logger.info("=" * 60)
    logger.info("Robot Control Backend started")
    logger.info("  ROS2_MODE: %s", os.environ.get("ROS2_MODE", "mock"))
    logger.info("  log_dir: %s", settings.log_dir)
    logger.info("  log_level: %s", settings.log_level)
    logger.info("  chassis_base_url: %s", settings.chassis_base_url)
    logger.info("  teach_data_dir: %s", settings.teach_data_dir)
    logger.info("  workflow_data_dir: %s", settings.workflow_data_dir)
    logger.info("=" * 60)
    yield

    # Shutdown
    await chassis_client.close()
    await chassis_poller.stop()
    await status_heartbeat.stop()
    if components.runtime is not None:
        await components.log_collector.stop()
        await components.joint_state_listener.stop()
        await components.topic_listener.stop()
        await components.motor_feedback_listener.stop()
        components.runtime.stop()
    logger.info("Application stopped")


def _install_request_logger(app: FastAPI) -> None:
    """Log each HTTP request with a human-friendly action description.

    For known routes we emit "执行示教点 [arm=left name=preset_1 method=moveJ] -> 200 [45ms]".
    Unknown routes still log method+path. Noisy polling endpoints are skipped
    unless they fail or exceed 1s.
    """
    import json as _json
    import time as _time

    from app.core.request_descriptor import describe_request

    SKIP_PATHS = (
        "/api/v1/robot/robot_001/status",
        "/api/v1/system/logs/backend",
        "/api/v1/system/logs/ros2-nodes",
        "/api/v1/robot/robot_001/camera/frame",
    )
    access_logger = logging.getLogger("app.access")

    async def _read_body(request) -> dict | None:
        """Buffer the request body so it can still be read by the route handler."""
        body_bytes = await request.body()
        if not body_bytes:
            return None
        # Re-inject the body for downstream handlers
        async def receive():
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        request._receive = receive
        try:
            return _json.loads(body_bytes)
        except (ValueError, UnicodeDecodeError):
            return None

    @app.middleware("http")
    async def _log_requests(request, call_next):
        start = _time.perf_counter()
        body = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            try:
                body = await _read_body(request)
            except Exception:
                body = None

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (_time.perf_counter() - start) * 1000
            desc = describe_request(request.method, request.url.path, body) \
                or f"{request.method} {request.url.path}"
            access_logger.exception(
                "%s -> 500 [%.1fms] from=%s",
                desc, duration_ms,
                request.client.host if request.client else "?",
            )
            raise

        duration_ms = (_time.perf_counter() - start) * 1000
        path = request.url.path
        is_get = request.method == "GET"
        is_noisy = path.startswith(SKIP_PATHS)
        is_slow = duration_ms > 1000
        is_error = response.status_code >= 400

        # Default: drop all successful GETs and SKIP_PATHS unless slow/failed
        skip = is_noisy or is_get
        if (not skip) or is_slow or is_error:
            desc = describe_request(request.method, path, body) \
                or f"{request.method} {path}"
            level = logging.WARNING if is_error else logging.INFO
            access_logger.log(
                level,
                "%s -> %d [%.1fms] from=%s",
                desc, response.status_code, duration_ms,
                request.client.host if request.client else "?",
            )
        return response


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0", lifespan=lifespan)
    _install_request_logger(app)
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    app.include_router(upper_body_router)
    app.include_router(workflow_router)
    app.include_router(camera_router)
    app.include_router(log_viewer_router)
    app.include_router(status_ws_router)
    app.include_router(logs_ws_router)
    app.include_router(camera_ws_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
