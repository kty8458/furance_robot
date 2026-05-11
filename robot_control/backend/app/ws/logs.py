from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.log_service import LogService

router = APIRouter()


@router.websocket("/ws/v1/logs")
async def logs_websocket(websocket: WebSocket):
    log_service: LogService = websocket.app.state.log_service
    await websocket.accept()
    log_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_service.remove_connection(websocket)
