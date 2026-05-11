from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.status_service import StatusService

router = APIRouter()


@router.websocket("/ws/v1/status")
async def status_websocket(websocket: WebSocket):
    status_service: StatusService = websocket.app.state.status_service
    await websocket.accept()
    status_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        status_service.remove_connection(websocket)
