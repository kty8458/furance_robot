import json
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/dispatch", tags=["status"])

_proxy = RobotProxyService()


class RobotRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    control_url: str
    ws_url: str


@router.get("/robots", response_model=ApiResponse)
async def list_robots(request: Request):
    db = request.app.state.db
    robots = await db.fetch_all("SELECT * FROM robots")
    if not robots:
        return ApiResponse(data={"robots": []})
    # Attach latest status from robot_status table
    for robot in robots:
        status_row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot["id"],))
        if status_row:
            robot["status"] = {
                "battery": status_row["battery"],
                "charging": bool(status_row["charging"]),
                "enabled": bool(status_row["enabled"]),
                "error_code": status_row["error_code"],
                "task_status": status_row["task_status"],
                "updated_at": status_row["updated_at"],
            }
        else:
            robot["status"] = None
    return ApiResponse(data={"robots": robots})


@router.post("/robots", response_model=ApiResponse)
async def register_robot(req: RobotRegister, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (req.id,))
    if existing:
        return ApiResponse(code=3001, message=f"Robot {req.id} already exists")
    await db.execute(
        "INSERT INTO robots (id, name, control_url, ws_url) VALUES (?, ?, ?, ?)",
        (req.id, req.name, req.control_url, req.ws_url),
    )
    return ApiResponse(data={"id": req.id, "name": req.name})


@router.delete("/robots/{robot_id}", response_model=ApiResponse)
async def delete_robot(robot_id: str, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (robot_id,))
    if not existing:
        return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
    await db.execute("DELETE FROM robots WHERE id = ?", (robot_id,))
    await db.execute("DELETE FROM robot_status WHERE robot_id = ?", (robot_id,))
    return ApiResponse(data={"deleted": robot_id})
