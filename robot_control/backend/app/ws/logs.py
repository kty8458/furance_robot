from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.log_service import LogService

router = APIRouter()
_log_service = LogService()


@router.websocket("/ws/v1/logs")
async def logs_websocket(websocket: WebSocket):
    await websocket.accept()
    _log_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _log_service.remove_connection(websocket)


def get_log_service() -> LogService:
    return _log_service
