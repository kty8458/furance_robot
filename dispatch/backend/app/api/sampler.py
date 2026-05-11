from fastapi import APIRouter
from pydantic import BaseModel
from furance_shared.protocol.http_schema import ApiResponse
from app.services.sampler_service import SamplerService

router = APIRouter(prefix="/api/v1/sampler", tags=["sampler"])


class SamplerCommand(BaseModel):
    command: str
    params: dict = {}


@router.post("/command", response_model=ApiResponse)
async def sampler_command(cmd: SamplerCommand):
    service = SamplerService()
    if cmd.command == "start":
        return await service.start()
    elif cmd.command == "stop":
        return await service.stop()
    elif cmd.command == "query":
        return await service.query()
    return ApiResponse(code=3002, message=f"Unknown command: {cmd.command}")


@router.get("/status", response_model=ApiResponse)
async def sampler_status():
    service = SamplerService()
    return await service.query()