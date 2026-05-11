from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.navigation import router as nav_router
from app.api.task import router as task_router
from app.api.sampler import router as sampler_router
from app.api.status import router as status_router


def create_app() -> FastAPI:
    app = FastAPI(title="Dispatch System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(nav_router)
    app.include_router(task_router)
    app.include_router(sampler_router)
    app.include_router(status_router)
    return app


app = create_app()