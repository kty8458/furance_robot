from fastapi import FastAPI
from app.api.robot import router as robot_router
from app.api.arm import router as arm_router
from app.api.navigation import router as nav_router
from app.api.ros2_nodes import router as ros2_router


def create_app() -> FastAPI:
    app = FastAPI(title="Robot Control System", version="0.1.0")
    app.include_router(robot_router)
    app.include_router(arm_router)
    app.include_router(nav_router)
    app.include_router(ros2_router)
    return app


app = create_app()
