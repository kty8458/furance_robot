import asyncio
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from furance_shared.protocol.ws_frames import StatusFrame
from furance_shared.models.robot import Position, GripperInfo, GripperState, ArmState
from app.services.status_service import StatusService

router = APIRouter()
_status_service = StatusService()


@router.websocket("/ws/v1/status")
async def status_websocket(websocket: WebSocket):
    await websocket.accept()
    _status_service.add_connection(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _status_service.remove_connection(websocket)


def get_status_service() -> StatusService:
    return _status_service
