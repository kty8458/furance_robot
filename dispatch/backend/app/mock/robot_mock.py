import asyncio
import json
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.mock.config import MockConfig

logger = logging.getLogger(__name__)

# ── Random data generators ──

def random_position():
    return {"x": round(random.uniform(0, 10), 2), "y": round(random.uniform(0, 10), 2), "theta": round(random.uniform(-3.14, 3.14), 2)}

def random_gripper():
    state = random.choice(["open", "closed"])
    return {
        "left": {"state": state, "force": round(random.uniform(0, 50), 1)},
        "right": {"state": random.choice(["open", "closed"]), "force": round(random.uniform(0, 50), 1)},
    }

def random_arm():
    return {
        "left": {"joint_angles": [round(random.uniform(-1.5, 1.5), 2) for _ in range(7)], "status": random.choice(["idle", "running"])},
        "right": {"joint_angles": [round(random.uniform(-1.5, 1.5), 2) for _ in range(7)], "status": random.choice(["idle", "running"])},
    }

def random_status():
    return {
        "position": random_position(),
        "current_map": "workshop_map",
        "lift_height": round(random.uniform(0, 500), 0),
        "gripper": random_gripper(),
        "battery": random.randint(10, 100),
        "charging": random.choice([True, False]),
        "enabled": True,
        "error_code": 0,
        "task_status": "idle",
        "arm": random_arm(),
    }


# ── FastAPI app ──

config = MockConfig()
connections: list[WebSocket] = []
active_executions: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    status_task = asyncio.create_task(status_pusher())
    log_task = asyncio.create_task(log_pusher())
    logger.info("Mock robot background pushers started")
    yield
    status_task.cancel()
    log_task.cancel()


mock_app = FastAPI(title="Mock Robot Control System", lifespan=lifespan)


# Background task: push status periodically
async def status_pusher():
    while True:
        await asyncio.sleep(config.status_interval)
        frame = {
            "type": "status",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": random_status(),
        }
        await _broadcast(frame)


async def log_pusher():
    messages = [
        "Joint state updated", "Navigation status normal", "Battery level check OK",
        "Motor temperature normal", "Lidar scan completed", "IMU calibration OK",
        "ROS2 node heartbeat", "Camera frame captured",
    ]
    while True:
        await asyncio.sleep(random.uniform(3.0, 10.0))
        frame = {
            "type": "log",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "level": random.choice(["info", "info", "info", "warn"]),
                "source": random.choice(["move_node", "arm_node", "status_node", "camera_node"]),
                "node": "mock",
                "message": random.choice(messages),
            },
        }
        await _broadcast(frame)


async def _broadcast(frame: dict):
    dead = []
    for ws in connections:
        try:
            await ws.send_json(frame)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in connections:
            connections.remove(ws)


# ── WebSocket endpoint ──

@mock_app.websocket("/ws/v1/status")
async def ws_status(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)


# ── HTTP API endpoints ──

@mock_app.get("/api/v1/robot/{robot_id}/status")
async def get_status(robot_id: str):
    return {"code": 0, "message": "ok", "data": random_status()}


@mock_app.get("/api/v1/robot/{robot_id}/workflows")
async def list_workflows(robot_id: str):
    return {"code": 0, "message": "ok", "data": [
        {"name": "sample_collect", "description": "取样流程", "step_count": 4, "version": 1},
        {"name": "move_to_charge", "description": "移动充电", "step_count": 2, "version": 1},
        {"name": "inspect_route", "description": "巡检路线", "step_count": 6, "version": 1},
    ]}


@mock_app.get("/api/v1/robot/{robot_id}/workflows/{name}")
async def get_workflow(robot_id: str, name: str):
    nav_presets = {
        "sample_collect": {"map_name": "workshop_map", "point_name": "sample_station"},
        "move_to_charge": {"map_name": "workshop_map", "point_name": "charge_dock"},
        "inspect_route": {"map_name": "workshop_map", "path_name": "inspect_loop", "path_type": "NavigationPathTask"},
    }
    nav = nav_presets.get(name, {"map_name": "workshop_map", "point_name": "home"})
    move_config = {"mode": "path" if "path_name" in nav else "point", **nav}
    return {"code": 0, "message": "ok", "data": {
        "name": name,
        "description": f"Mock workflow: {name}",
        "steps": [
            {"id": "step_1", "type": "move", "label": "导航至目标点", "config": move_config},
            {"id": "step_2", "type": "upper_limb", "label": "手臂移动", "config": {"mode": "preset", "arm": "left", "preset_name": "home"}},
            {"id": "step_3", "type": "gripper", "label": "夹爪闭合", "config": {"arm": "left", "action": "close"}},
            {"id": "step_4", "type": "sleep", "label": "等待", "config": {"duration": 2.0}},
        ],
        "version": 1,
    }}


@mock_app.post("/api/v1/robot/{robot_id}/workflows/{name}/execute")
async def execute_workflow(robot_id: str, name: str):
    execution_id = str(uuid.uuid4())
    workflow_steps = [
        {"id": "step_1", "label": "导航至目标点", "total_steps": 4, "index": 1},
        {"id": "step_2", "label": "手臂移动", "total_steps": 4, "index": 2},
        {"id": "step_3", "label": "夹爪闭合", "total_steps": 4, "index": 3},
        {"id": "step_4", "label": "等待完成", "total_steps": 4, "index": 4},
    ]
    active_executions[execution_id] = {
        "execution_id": execution_id,
        "name": name,
        "status": "running",
        "active": True,
        "current_step_index": 0,
        "current_step_id": None,
        "current_step_label": None,
        "total_steps": len(workflow_steps),
        "started_at": time.time(),
        "completed_at": None,
        "error_msg": None,
    }
    asyncio.create_task(_run_mock_workflow(execution_id, name, workflow_steps))
    return {"code": 0, "message": "ok", "data": {"execution_id": execution_id, "status": "started"}}


async def _run_mock_workflow(execution_id: str, name: str, steps: list[dict]):
    state = active_executions[execution_id]
    for step in steps:
        if state.get("status") == "cancelled":
            state["active"] = False
            state["completed_at"] = time.time()
            return

        state["current_step_index"] = step["index"]
        state["current_step_id"] = step["id"]
        state["current_step_label"] = step["label"]

        # Push "running"
        await _broadcast({
            "type": "workflow_step",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "workflow_name": name,
                "execution_id": execution_id,
                "step_id": step["id"],
                "step_index": step["index"],
                "total_steps": step["total_steps"],
                "status": "running",
                "message": f"Executing: {step['label']}",
                "data": {},
            },
        })

        # Simulate work in 0.2s ticks so cancel responds quickly
        duration = random.uniform(config.step_duration_min, config.step_duration_max)
        elapsed = 0.0
        while elapsed < duration:
            if state.get("status") == "cancelled":
                state["active"] = False
                state["completed_at"] = time.time()
                return
            await asyncio.sleep(0.2)
            elapsed += 0.2

        # Random error
        if random.random() < config.error_probability:
            await _broadcast({
                "type": "workflow_step",
                "robot_id": config.robot_id,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "workflow_name": name,
                    "execution_id": execution_id,
                    "step_id": step["id"],
                    "step_index": step["index"],
                    "total_steps": step["total_steps"],
                    "status": "failed",
                    "message": f"Step failed: {step['label']}",
                    "data": {},
                },
            })
            state["status"] = "failed"
            state["active"] = False
            state["error_msg"] = f"Step failed: {step['label']}"
            state["completed_at"] = time.time()
            return

        # Random alarm
        if random.random() < config.alarm_probability:
            level = "critical" if random.random() < config.critical_alarm_ratio else "warning"
            await _broadcast({
                "type": "alarm",
                "robot_id": config.robot_id,
                "timestamp": int(time.time() * 1000),
                "payload": {
                    "alarm_id": str(uuid.uuid4()),
                    "level": level,
                    "category": random.choice(["arm", "chassis", "battery", "gripper"]),
                    "title": f"Mock {level} alarm",
                    "message": f"Simulated {level} during step: {step['label']}",
                    "source": "robot_control",
                },
            })

        # Push "completed"
        await _broadcast({
            "type": "workflow_step",
            "robot_id": config.robot_id,
            "timestamp": int(time.time() * 1000),
            "payload": {
                "workflow_name": name,
                "execution_id": execution_id,
                "step_id": step["id"],
                "step_index": step["index"],
                "total_steps": step["total_steps"],
                "status": "completed",
                "message": f"Completed: {step['label']}",
                "data": {},
            },
        })

    state["status"] = "completed"
    state["active"] = False
    state["completed_at"] = time.time()


@mock_app.post("/api/v1/robot/{robot_id}/workflows/{name}/cancel")
async def cancel_workflow(robot_id: str, name: str):
    for eid, exec_data in list(active_executions.items()):
        if exec_data["name"] == name and exec_data["status"] == "running":
            exec_data["status"] = "cancelled"
    return {"code": 0, "message": "ok", "data": {"cancelled": True}}


@mock_app.get("/api/v1/robot/{robot_id}/workflows/executions/{execution_id}")
async def get_execution(robot_id: str, execution_id: str):
    if execution_id in active_executions:
        return {"code": 0, "message": "ok", "data": active_executions[execution_id]}
    return {"code": 3002, "message": "Execution not found", "data": None}


# Generic mock for other endpoints
@mock_app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(path: str):
    return {"code": 0, "message": f"mock: {path}", "data": {}}


def create_mock_app():
    return mock_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.mock.robot_mock:mock_app", host="0.0.0.0", port=config.port, reload=False)
