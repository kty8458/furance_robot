from fastapi import APIRouter, Query, Request
from furance_shared.protocol.http_schema import ApiResponse

router = APIRouter(prefix="/api/v1/dispatch/logs", tags=["logs"])


@router.get("", response_model=ApiResponse)
async def list_logs(
    request: Request,
    level: str = Query(None),
    source: str = Query(None),
    robot_id: str = Query(None),
):
    logs = await request.app.state.log_service.list_logs(
        level=level, source=source, robot_id=robot_id,
    )
    return ApiResponse(data=logs)
