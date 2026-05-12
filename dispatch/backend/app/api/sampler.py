import time

from fastapi import APIRouter, Request
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse
from app.services.sampler_service import SamplerService

router = APIRouter(prefix="/api/v1/dispatch/sampler", tags=["sampler"])


class SamplerCommand(BaseModel):
    command: str
    params: dict = {}


MOCK_SAMPLER_STATUS = {
    "status": "idle",
    "progress": 0,
    "current_step": "",
    "total_steps": 5,
}


def _get_db(request: Request):
    return request.app.state.db


async def _save_sampler_status(request: Request, data: dict):
    db = _get_db(request)
    now = time.time()
    await db.execute(
        "INSERT OR REPLACE INTO sampler_status (id, status, progress, last_update) VALUES (1, ?, ?, ?)",
        (data.get("status", "idle"), data.get("progress", 0), now),
    )


async def _read_sampler_status(request: Request) -> dict | None:
    db = _get_db(request)
    row = await db.fetch_one("SELECT * FROM sampler_status WHERE id = 1")
    if not row:
        return None
    return {
        "status": row["status"],
        "progress": row["progress"],
        "last_update": row["last_update"],
    }


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand, request: Request):
    try:
        service = SamplerService()
        if cmd.command == "start":
            result = await service.start()
        elif cmd.command == "stop":
            result = await service.stop()
        elif cmd.command == "query":
            result = await service.query()
        else:
            return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")
        if result.code == 0 and result.data:
            await _save_sampler_status(request, result.data)
        return result
    except Exception:
        await _save_sampler_status(request, MOCK_SAMPLER_STATUS)
        return ApiResponse(data=MOCK_SAMPLER_STATUS)


@router.get("/status", response_model=ApiResponse)
async def sampler_status(request: Request):
    # Try live data
    try:
        service = SamplerService()
        result = await service.query()
        if result.code == 0 and result.data:
            await _save_sampler_status(request, result.data)
            return result
    except Exception:
        pass
    # Fallback: DB
    db_status = await _read_sampler_status(request)
    if db_status:
        return ApiResponse(data=db_status)
    # Last fallback: mock
    return ApiResponse(data=MOCK_SAMPLER_STATUS)
