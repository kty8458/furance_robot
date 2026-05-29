import json

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/robots", tags=["robots"])


class RobotRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    control_url: str
    ws_url: str


@router.get("", response_model=ApiResponse)
async def list_robots(request: Request):
    db = request.app.state.db
    robots = await db.fetch_all("SELECT * FROM robots")
    for robot in robots:
        status_row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot["id"],))
        robot["status_data"] = None
        robot["status"] = "offline"
        if status_row:
            robot["status_data"] = json.loads(status_row["status_json"])
            robot["status"] = "online"
    return ApiResponse(data={"robots": robots})


@router.get("/{robot_id}/status", response_model=ApiResponse)
async def get_robot_status(robot_id: str, request: Request):
    db = request.app.state.db
    status_row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot_id,))
    if not status_row:
        return ApiResponse(code=3002, message=f"Robot {robot_id} status not found")
    return ApiResponse(data={
        "robot_id": robot_id,
        "status": json.loads(status_row["status_json"]),
        "updated_at": status_row["updated_at"],
    })


@router.post("", response_model=ApiResponse)
async def register_robot(req: RobotRegister, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (req.id,))
    if existing:
        return ApiResponse(code=3001, message=f"Robot {req.id} already exists")
    await db.execute(
        "INSERT INTO robots (id, name, control_url, ws_url) VALUES (?, ?, ?, ?)",
        (req.id, req.name, req.control_url, req.ws_url),
    )
    if hasattr(request.app.state, 'status_monitor'):
        await request.app.state.status_monitor.register_robot(req.id, req.ws_url)
    return ApiResponse(data={"id": req.id, "name": req.name})


@router.delete("/{robot_id}", response_model=ApiResponse)
async def delete_robot(robot_id: str, request: Request):
    db = request.app.state.db
    existing = await db.fetch_one("SELECT id FROM robots WHERE id = ?", (robot_id,))
    if not existing:
        return ApiResponse(code=3002, message=f"Robot {robot_id} not found")
    await db.execute("DELETE FROM robots WHERE id = ?", (robot_id,))
    await db.execute("DELETE FROM robot_status WHERE robot_id = ?", (robot_id,))
    return ApiResponse(data={"deleted": robot_id})


@router.get("/{robot_id}/workflows", response_model=ApiResponse)
async def list_robot_workflows(robot_id: str, request: Request):
    proxy = request.app.state.robot_proxy
    return await proxy.forward_get(robot_id, f"/api/v1/robot/{robot_id}/workflows")


@router.get("/{robot_id}/workflows/{name}", response_model=ApiResponse)
async def get_robot_workflow(robot_id: str, name: str, request: Request):
    proxy = request.app.state.robot_proxy
    return await proxy.forward_get(robot_id, f"/api/v1/robot/{robot_id}/workflows/{name}")


@router.post("/{robot_id}/workflows/{name}/execute", response_model=ApiResponse)
async def execute_robot_workflow(robot_id: str, name: str, request: Request):
    proxy = request.app.state.robot_proxy
    return await proxy.forward(
        robot_id,
        f"/api/v1/robot/{robot_id}/workflows/{name}/execute",
        {"nav_params": []},
    )
