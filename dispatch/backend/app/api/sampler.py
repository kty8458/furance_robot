import json
import time

from fastapi import APIRouter, Request
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/sampler", tags=["sampler"])


class SamplerCommand(BaseModel):
    command: str
    params: dict = {}


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand, request: Request):
    service = request.app.state.sampler_service
    if cmd.command == "start":
        result = await service.start()
    elif cmd.command == "stop":
        result = await service.stop()
    elif cmd.command == "query":
        result = await service.query()
    else:
        return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")
    if result.code == 0 and result.data:
        now = time.time()
        db = request.app.state.db
        await db.execute(
            "INSERT OR REPLACE INTO sampler_status (id, status, progress, status_json, last_update) VALUES (1, ?, ?, ?, ?)",
            (result.data.get("status", "idle"), result.data.get("progress", 0),
             json.dumps(result.data), now),
        )
    return result


@router.get("/status", response_model=ApiResponse)
async def sampler_status(request: Request):
    db = request.app.state.db
    row = await db.fetch_one("SELECT * FROM sampler_status WHERE id = 1")
    if not row:
        return ApiResponse(data={"status": "idle", "progress": 0})
    return ApiResponse(data={
        "status": row["status"],
        "progress": row["progress"],
        "status_data": json.loads(row["status_json"]) if row["status_json"] else {},
        "last_update": row["last_update"],
    })
