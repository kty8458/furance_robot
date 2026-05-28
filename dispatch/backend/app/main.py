import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.api.robots import router as robots_router
from app.api.task import router as task_router
from app.api.executions import router as executions_router
from app.api.alarms import router as alarms_router
from app.api.logs import router as logs_router
from app.api.sampler import router as sampler_router
from app.core.database import Database
from app.core.config import get_settings
from app.services.task_editor import TaskEditor
from app.services.task_executor import TaskExecutor
from app.services.alarm_service import AlarmService
from app.services.status_monitor import StatusMonitor
from app.services.log_service import LogService
from app.services.robot_proxy import RobotProxyService
from app.services.sampler_service import SamplerService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    db_path = os.environ.get("DATABASE_PATH", settings.database_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    await db.init()
    app.state.db = db

    # WS broadcast connections
    app.state.ws_connections: list[WebSocket] = []

    # Services
    robot_proxy = RobotProxyService()
    robot_proxy.set_db(db)
    sampler_service = SamplerService()
    alarm_service = AlarmService(db)
    status_monitor = StatusMonitor(db, alarm_service)
    log_service = LogService(db)
    task_editor = TaskEditor(db)
    task_executor = TaskExecutor(db, robot_proxy, sampler_service)

    alarm_service._task_executor = task_executor

    app.state.robot_proxy = robot_proxy
    app.state.sampler_service = sampler_service
    app.state.alarm_service = alarm_service
    app.state.status_monitor = status_monitor
    app.state.log_service = log_service
    app.state.task_editor = task_editor
    app.state.task_executor = task_executor

    # Register robots from DB
    robots = await db.fetch_all("SELECT * FROM robots")
    for robot in robots:
        await status_monitor.register_robot(robot["id"], robot["ws_url"])

    # Seed default alarm rules if empty
    rules = await db.fetch_all("SELECT id FROM alarm_rules")
    if not rules:
        now = time.time()
        await db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("低电量警告", "battery", "warning", '{"field": "battery", "operator": "<", "value": 20}', 1, now),
        )
        await db.execute(
            "INSERT INTO alarm_rules (name, category, level, condition_json, enabled, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("电量耗尽", "battery", "critical", '{"field": "battery", "operator": "<", "value": 5}', 1, now),
        )

    logger.info("Dispatch system started, database: %s", db_path)
    yield
    # Shutdown
    await status_monitor.stop()
    await robot_proxy.close()
    await db.close()
    logger.info("Dispatch system stopped")


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Dispatch System", version="2.0.0", lifespan=lifespan)
    app.include_router(robots_router)
    app.include_router(task_router)
    app.include_router(executions_router)
    app.include_router(alarms_router)
    app.include_router(logs_router)
    app.include_router(sampler_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
