import asyncio
import json
import random
import time
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

MOCK_PORT = 9002

connections: list[WebSocket] = []
sampler_state = {"status": "idle", "progress": 0, "current_step": ""}

mock_app = FastAPI(title="Mock Sampler")


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


async def status_pusher():
    while True:
        await asyncio.sleep(3.0)
        if sampler_state["status"] == "running":
            sampler_state["progress"] = min(100, sampler_state["progress"] + random.randint(5, 20))
            if sampler_state["progress"] >= 100:
                sampler_state["status"] = "completed"
                sampler_state["progress"] = 100
        frame = {
            "type": "status",
            "payload": sampler_state.copy(),
        }
        await _broadcast(frame)


@mock_app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    connections.append(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "command":
                cmd = msg.get("command", "")
                if cmd == "start":
                    sampler_state["status"] = "running"
                    sampler_state["progress"] = 0
                    sampler_state["current_step"] = "processing"
                elif cmd == "stop":
                    sampler_state["status"] = "idle"
                    sampler_state["progress"] = 0
                    sampler_state["current_step"] = ""
                await ws.send_json({
                    "type": "response",
                    "request_id": msg.get("request_id", ""),
                    "payload": sampler_state.copy(),
                })
    except WebSocketDisconnect:
        if ws in connections:
            connections.remove(ws)


@mock_app.post("/api/v1/sampler/command")
async def sampler_command(cmd: dict):
    command = cmd.get("command", "")
    if command == "start":
        sampler_state["status"] = "running"
        sampler_state["progress"] = 0
        sampler_state["current_step"] = "processing"
    elif command == "stop":
        sampler_state["status"] = "idle"
        sampler_state["progress"] = 0
        sampler_state["current_step"] = ""
    return {"code": 0, "message": "ok", "data": sampler_state.copy()}


@mock_app.get("/api/v1/sampler/status")
async def sampler_status():
    return {"code": 0, "message": "ok", "data": sampler_state.copy()}


def create_mock_app():
    return mock_app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.mock.sampler_mock:mock_app", host="0.0.0.0", port=MOCK_PORT, reload=False)
