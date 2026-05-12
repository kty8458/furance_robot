import json
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from furance_shared.models.command import (
    MoveCommand, GrabCommand, PlaceCommand, GripperCommand,
    LiftCommand, ChargeCommand, EnableCommand,
)
from furance_shared.protocol.http_schema import ApiResponse
from app.services.robot_proxy import RobotProxyService

router = APIRouter(prefix="/api/v1/dispatch/robot/{robot_id}", tags=["robot"])

_proxy = RobotProxyService()


class RobotRegister(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    control_url: str
    ws_url: str


@router.post("/home", response_model=ApiResponse)
async def home(robot_id: str):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/home")


@router.post("/move", response_model=ApiResponse)
async def move(robot_id: str, cmd: MoveCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/move", cmd.model_dump())


@router.post("/grab", response_model=ApiResponse)
async def grab(robot_id: str, cmd: GrabCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/grab", cmd.model_dump())


@router.post("/place", response_model=ApiResponse)
async def place(robot_id: str, cmd: PlaceCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/place", cmd.model_dump())


@router.post("/gripper", response_model=ApiResponse)
async def gripper(robot_id: str, cmd: GripperCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/gripper", cmd.model_dump())


@router.post("/lift", response_model=ApiResponse)
async def lift(robot_id: str, cmd: LiftCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/lift", cmd.model_dump())


@router.post("/charge", response_model=ApiResponse)
async def charge(robot_id: str, cmd: ChargeCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/charge", cmd.model_dump())


@router.post("/enable", response_model=ApiResponse)
async def enable(robot_id: str, cmd: EnableCommand):
    return await _proxy.forward(robot_id, "/api/v1/robot/robot_001/enable", cmd.model_dump())


@router.get("/status", response_model=ApiResponse)
async def status(robot_id: str, request: Request):
    # Try live data first
    result = await _proxy.forward_get(robot_id, "/api/v1/robot/robot_001/status")
    if result.code == 0 and result.data:
        # Persist to DB
        await _save_robot_status(request, robot_id, result.data)
        return result
    # Fallback: read from DB
    db_status = await _read_robot_status(request, robot_id)
    if db_status:
        return ApiResponse(data=db_status)
    # Last fallback: mock
    return ApiResponse(data=_mock_robot_status(robot_id))


# ── Robot list CRUD (on /dispatch/robots) ──


def _get_db(request: Request):
    return request.app.state.db


async def _save_robot_status(request: Request, robot_id: str, data: dict):
    db = _get_db(request)
    now = time.time()
    await db.execute(
        """INSERT OR REPLACE INTO robot_status
           (robot_id, position_json, gripper_json, arm_json, battery, charging, enabled, error_code, task_status, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            robot_id,
            json.dumps(data.get("position", {})),
            json.dumps(data.get("gripper", {})),
            json.dumps(data.get("arm", {})),
            data.get("battery", 0),
            int(data.get("charging", False)),
            int(data.get("enabled", False)),
            data.get("error_code", 0),
            data.get("task_status", "idle"),
            now,
        ),
    )


async def _read_robot_status(request: Request, robot_id: str) -> dict | None:
    db = _get_db(request)
    row = await db.fetch_one("SELECT * FROM robot_status WHERE robot_id = ?", (robot_id,))
    if not row:
        return None
    return {
        "position": json.loads(row["position_json"]),
        "gripper": json.loads(row["gripper_json"]),
        "arm": json.loads(row["arm_json"]),
        "battery": row["battery"],
        "charging": bool(row["charging"]),
        "enabled": bool(row["enabled"]),
        "error_code": row["error_code"],
        "task_status": row["task_status"],
        "updated_at": row["updated_at"],
    }


def _mock_robot_status(robot_id: str) -> dict:
    return {
        "position": {"x": 1.23, "y": 4.56, "theta": 0.78},
        "current_map": "workshop_map",
        "lift_height": 0.0,
        "gripper": {
            "left": {"state": "open", "force": 0.0},
            "right": {"state": "open", "force": 0.0},
        },
        "battery": 85,
        "charging": False,
        "enabled": True,
        "error_code": 0,
        "task_status": "idle",
        "arm": {
            "left": {"joint_angles": [0.0] * 7, "status": "idle"},
            "right": {"joint_angles": [0.0] * 7, "status": "idle"},
        },
    }
