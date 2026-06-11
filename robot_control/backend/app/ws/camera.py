"""
WebSocket 相机推流转发器。

挂载到 /ws/v1/camera。接收前端的订阅请求，转发到
camera_manager_node 的内部 WebSocket (localhost:8766)，
将帧数据透传给前端。

协议 (与前端):
  前端 → {"action": "subscribe", "camera_id": "head", "stream_type": "raw"}
  前端 ← {"type": "frame", "camera_id": "head", "stream_type": "raw", "data": "<base64>"}
  前端 → {"action": "unsubscribe"}
"""

import asyncio
import json
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

CAMERA_WS_URL = "ws://127.0.0.1:8766"


@router.websocket("/ws/v1/camera")
async def camera_relay(ws: WebSocket):
    """转发前端 WS 请求到 camera_manager_node 的内部 WS。"""
    await ws.accept()

    upstream: websockets.WebSocketClientProtocol | None = None
    relay_task: asyncio.Task | None = None

    async def relay_upstream_to_frontend():
        """将 camera_manager_node 的消息透传给前端。"""
        try:
            while upstream is not None:
                try:
                    msg = await asyncio.wait_for(upstream.recv(), timeout=30.0)
                    await ws.send_text(msg)
                except asyncio.TimeoutError:
                    continue
                except websockets.ConnectionClosed:
                    break
        except Exception:
            pass

    try:
        while True:
            raw = await ws.receive_text()

            # 收到前端消息 → 转发给 camera_manager_node
            if upstream is None or not upstream.open:
                upstream = await websockets.connect(CAMERA_WS_URL)
                if relay_task:
                    relay_task.cancel()
                relay_task = asyncio.create_task(relay_upstream_to_frontend())

            await upstream.send(raw)

    except WebSocketDisconnect:
        logger.info("Camera WS relay: frontend disconnected")
    except Exception:
        logger.exception("Camera WS relay error")
    finally:
        if relay_task:
            relay_task.cancel()
        if upstream and upstream.open:
            await upstream.close()
