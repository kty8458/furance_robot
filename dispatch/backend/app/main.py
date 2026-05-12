import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.robot import router as robot_router
from app.api.navigation import router as nav_router
from app.api.task import router as task_router
from app.api.sampler import router as sampler_router
from app.api.status import router as status_router
from app.core.database import Database
from app.core.config import get_settings

logger = logging.getLogger(__name__)

SEED_TEMPLATES = [
    {
        "id": "auto_sample",
        "name": "自动制样流程",
        "steps_json": '{"steps": [{"order": 1, "action": "robot.home", "params": {}}, {"order": 2, "action": "robot.grab", "params": {"target": "sample_pos"}}, {"order": 3, "action": "robot.move", "params": {"map_id": "workshop_map", "waypoint_id": "wp_02"}}, {"order": 4, "action": "sampler.start", "params": {}}, {"order": 5, "action": "wait_sampler_complete", "params": {}}]}',
    },
    {
        "id": "charge_and_wait",
        "name": "充电等待",
        "steps_json": '{"steps": [{"order": 1, "action": "robot.move", "params": {"map_id": "workshop_map", "waypoint_id": "wp_03"}}, {"order": 2, "action": "robot.charge", "params": {"action": "start"}}, {"order": 3, "action": "delay", "params": {"seconds": 60}}, {"order": 4, "action": "robot.charge", "params": {"action": "stop"}}]}',
    },
    {
        "id": "grab_place_cycle",
        "name": "抓放循环",
        "steps_json": '{"steps": [{"order": 1, "action": "robot.home", "params": {}}, {"order": 2, "action": "robot.grab", "params": {"target": "input_pos"}}, {"order": 3, "action": "robot.place", "params": {"target": "output_pos"}}]}',
    },
]


async def seed_database(db: Database):
    """Insert seed data if tables are empty."""
    now = time.time()

    # Seed templates
    rows = await db.fetch_all("SELECT id FROM task_templates")
    if not rows:
        for t in SEED_TEMPLATES:
            await db.execute(
                "INSERT OR IGNORE INTO task_templates (id, name, steps_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (t["id"], t["name"], t["steps_json"], now, now),
            )
        logger.info("Seeded %d task templates", len(SEED_TEMPLATES))

    # Seed robots from config
    rows = await db.fetch_all("SELECT id FROM robots")
    if not rows:
        settings = get_settings()
        for r in settings.robots:
            await db.execute(
                "INSERT OR IGNORE INTO robots (id, name, control_url, ws_url) VALUES (?, ?, ?, ?)",
                (r.id, r.name, r.control_url, r.ws_url),
            )
        # Extra mock robots
        await db.execute(
            "INSERT OR IGNORE INTO robots (id, name, control_url, ws_url) VALUES (?, ?, ?, ?)",
            ("robot_002", "2号机器人", "http://192.168.1.101:8000", "ws://192.168.1.101:8000/ws/v1/status"),
        )
        logger.info("Seeded robots from config + mock data")

    # Seed robot_status
    rows = await db.fetch_all("SELECT robot_id FROM robot_status")
    if not rows:
        await db.execute(
            """INSERT INTO robot_status (robot_id, position_json, gripper_json, arm_json, battery, charging, enabled, error_code, task_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "robot_001",
                '{"x": 3.25, "y": 1.78, "theta": 0.52}',
                '{"left": {"state": "open", "force": 0.0}, "right": {"state": "open", "force": 0.0}}',
                '{"left": {"joint_angles": [0.0, -0.5, 0.3, 0.0, 0.2, 0.0, 0.0], "status": "idle"}, "right": {"joint_angles": [0.0, -0.5, 0.3, 0.0, 0.2, 0.0, 0.0], "status": "idle"}}',
                85, 0, 1, 0, "idle", now,
            ),
        )
        await db.execute(
            """INSERT INTO robot_status (robot_id, position_json, gripper_json, arm_json, battery, charging, enabled, error_code, task_status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "robot_002",
                '{"x": 5.60, "y": 2.10, "theta": -1.23}',
                '{"left": {"state": "closed", "force": 32.5}, "right": {"state": "open", "force": 0.0}}',
                '{"left": {"joint_angles": [0.2, -0.8, 0.5, -0.1, 0.3, 0.0, 0.0], "status": "running"}, "right": {"joint_angles": [0.0, -0.5, 0.3, 0.0, 0.2, 0.0, 0.0], "status": "idle"}}',
                42, 1, 1, 0, "running", now,
            ),
        )
        logger.info("Seeded robot_status mock data")

    # Seed sampler_status
    rows = await db.fetch_all("SELECT id FROM sampler_status")
    if not rows:
        await db.execute(
            "INSERT INTO sampler_status (status, progress, last_update) VALUES (?, ?, ?)",
            ("idle", 0, now),
        )
        logger.info("Seeded sampler_status mock data")

    # Seed task_executions with step logs
    rows = await db.fetch_all("SELECT id FROM task_executions")
    if not rows:
        # Completed execution
        await db.execute(
            "INSERT INTO task_executions (task_template_id, robot_id, status, started_at, completed_at) VALUES (?, ?, ?, ?, ?)",
            ("auto_sample", "robot_001", "completed", now - 3600, now - 3500),
        )
        for step in [
            (1, "robot.home", '{"order":1,"action":"robot.home","params":{}}', '{"code":0}', "completed"),
            (2, "robot.grab", '{"order":2,"action":"robot.grab","params":{"target":"sample_pos"}}', '{"code":0}', "completed"),
            (3, "robot.move", '{"order":3,"action":"robot.move","params":{"map_id":"workshop_map","waypoint_id":"wp_02"}}', '{"code":0}', "completed"),
            (4, "sampler.start", '{"order":4,"action":"sampler.start","params":{}}', '{"code":0}', "completed"),
            (5, "wait_sampler_complete", '{"order":5,"action":"wait_sampler_complete","params":{}}', '{"code":0}', "completed"),
        ]:
            await db.execute(
                "INSERT INTO task_step_logs (execution_id, step_order, action, params_json, result_json, status, started_at, completed_at) VALUES (1, ?, ?, ?, ?, ?, ?, ?)",
                (step[0], step[1], step[2], step[3], step[4], now - 3600 + step[0] * 120, now - 3600 + step[0] * 120 + 100),
            )

        # Failed execution
        await db.execute(
            "INSERT INTO task_executions (task_template_id, robot_id, status, started_at, completed_at, error_msg) VALUES (?, ?, ?, ?, ?, ?)",
            ("grab_place_cycle", "robot_001", "failed", now - 1800, now - 1750, "Step 2 (robot.grab) failed"),
        )
        for step in [
            (1, "robot.home", '{"order":1,"action":"robot.home","params":{}}', '{"code":0}', "completed"),
            (2, "robot.grab", '{"order":2,"action":"robot.grab","params":{"target":"input_pos"}}', '{"code":2001,"message":"Gripper timeout"}', "failed"),
        ]:
            await db.execute(
                "INSERT INTO task_step_logs (execution_id, step_order, action, params_json, result_json, status, started_at, completed_at) VALUES (2, ?, ?, ?, ?, ?, ?, ?)",
                (step[0], step[1], step[2], step[3], step[4], now - 1800 + step[0] * 60, now - 1800 + step[0] * 60 + 45),
            )

        # Running execution
        await db.execute(
            "INSERT INTO task_executions (task_template_id, robot_id, status, started_at) VALUES (?, ?, ?, ?)",
            ("charge_and_wait", "robot_002", "running", now - 300),
        )
        for step in [
            (1, "robot.move", '{"order":1,"action":"robot.move","params":{"map_id":"workshop_map","waypoint_id":"wp_03"}}', '{"code":0}', "completed"),
            (2, "robot.charge", '{"order":2,"action":"robot.charge","params":{"action":"start"}}', '{"code":0}', "completed"),
            (3, "delay", '{"order":3,"action":"delay","params":{"seconds":60}}', None, "running"),
        ]:
            await db.execute(
                "INSERT INTO task_step_logs (execution_id, step_order, action, params_json, result_json, status, started_at, completed_at) VALUES (3, ?, ?, ?, ?, ?, ?, ?)",
                (step[0], step[1], step[2], step[3], step[4], now - 300 + step[0] * 90, now - 300 + step[0] * 90 + 60 if step[4] == "completed" else None),
            )
        logger.info("Seeded task_executions + step_logs mock data")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings = get_settings()
    db_path = os.environ.get("DATABASE_PATH", settings.database_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    await db.init()
    await seed_database(db)
    app.state.db = db
    logger.info("Database initialized: %s", db_path)
    yield
    # Shutdown
    await db.close()
    logger.info("Database closed")


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Dispatch System", version="0.1.0", lifespan=lifespan)
    app.include_router(robot_router)
    app.include_router(nav_router)
    app.include_router(task_router)
    app.include_router(sampler_router)
    app.include_router(status_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
