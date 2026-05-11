import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router
from app.ws.status import router as status_ws_router
from app.ws.logs import router as logs_ws_router


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    app.include_router(status_ws_router)
    app.include_router(logs_ws_router)

    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


static_dir = os.environ.get("STATIC_DIR")
app = create_app(static_dir=static_dir)
