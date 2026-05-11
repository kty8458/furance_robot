import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.robot import router as robot_router
from app.api.navigation import router as nav_router
from app.api.task import router as task_router
from app.api.sampler import router as sampler_router
from app.api.status import router as status_router


def create_app(static_dir: str | None = None) -> FastAPI:
    app = FastAPI(title="Dispatch System", version="0.1.0")
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