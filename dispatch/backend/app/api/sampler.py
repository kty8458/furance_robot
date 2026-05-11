from fastapi import APIRouter
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


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand):
    try:
        service = SamplerService()
        if cmd.command == "start":
            return await service.start()
        elif cmd.command == "stop":
            return await service.stop()
        elif cmd.command == "query":
            return await service.query()
        return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")
    except Exception:
        # Return mock response when sampler is unreachable
        return ApiResponse(data=MOCK_SAMPLER_STATUS)


@router.get("/status", response_model=ApiResponse)
async def sampler_status():
    try:
        service = SamplerService()
        result = await service.query()
        if result.code != 0:
            return ApiResponse(data=MOCK_SAMPLER_STATUS)
        return result
    except Exception:
        return ApiResponse(data=MOCK_SAMPLER_STATUS)
